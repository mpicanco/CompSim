from __future__ import annotations

import asyncio
import threading

from .base import IOBackend, to_device, from_device


class OPCUABackend(IOBackend):
    """OPC UA client (via asyncua), running on its own asyncio loop thread.

    config keys: url (opc.tcp://host:4840). ``tag.address`` holds a NodeId
    string such as "ns=2;i=5" or "ns=2;s=TagName".
    """

    type = "opcua"

    def __init__(self, config):
        super().__init__(config)
        self.url = config.get("url", "opc.tcp://127.0.0.1:4840")
        self._client = None
        self._loop = None
        self._thread = None
        self._vtypes = {}   # NodeId string -> ua.VariantType of the node

    def connect(self):
        import asyncua

        self._asyncua = asyncua
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="opcua-loop")
        self._thread.start()
        try:
            self._submit(self._connect_coro()).result(timeout=10)
        except BaseException:
            self._shutdown_loop()   # do not leak a loop thread per failed attempt
            self._client = None
            raise
        self._vtypes.clear()
        self._connected = True
        self.status = "connected"

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _shutdown_loop(self):
        loop, thread = self._loop, self._thread
        self._loop = None
        self._thread = None
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        if loop is not None and not loop.is_running():
            loop.close()

    async def _connect_coro(self):
        self._client = self._asyncua.Client(url=self.url)
        await self._client.connect()

    def disconnect(self):
        if self._client is not None and self._loop is not None:
            try:
                self._submit(self._client.disconnect()).result(timeout=5)
            except Exception:
                pass
        self._shutdown_loop()
        self._client = None
        self._connected = False
        self.status = "disconnected"

    def _run(self, coro, timeout=5):
        if self._client is None or self._loop is None:
            self._connected = False
            raise ConnectionError("not connected")
        try:
            return self._submit(coro).result(timeout=timeout)
        except (ConnectionError, OSError, asyncio.TimeoutError, TimeoutError):
            self.disconnect()   # let the scan thread reconnect
            raise

    def read(self, tag):
        node = self._client.get_node(tag.address)
        raw = self._run(node.read_value())
        return from_device(raw, tag)

    async def _write_coro(self, node, nodeid, raw):
        ua = self._asyncua.ua
        vtype = self._vtypes.get(nodeid)
        if vtype is None:
            vtype = await node.read_data_type_as_variant_type()
            self._vtypes[nodeid] = vtype
        # cast to the node's declared type (servers reject Double -> Float etc.)
        if vtype == ua.VariantType.Boolean:
            raw = bool(raw)
        elif vtype in (ua.VariantType.Float, ua.VariantType.Double):
            raw = float(raw)
        elif vtype.name.startswith(("Int", "UInt", "SByte", "Byte")):
            raw = int(round(raw))
        await node.write_value(ua.DataValue(ua.Variant(raw, vtype)))

    def write(self, tag, value):
        node = self._client.get_node(tag.address)
        self._run(self._write_coro(node, tag.address, to_device(value, tag)))
