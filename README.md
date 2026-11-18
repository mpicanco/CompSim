<div align="center">

# ⚙️ CompSim

**Dynamic chemical process simulator with a node-based GUI**

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)

[Features](#-features) •
[Installation](#-installation) •
[Quick start](#-quick-start) •
[PLC integration](#-plc-integration) •
[Scripting](#-using-the-core-without-the-gui) •
[Contributing](#-contributing)

</div>

<!--
  Add a screenshot here once available, for example:
  <p align="center"><img src="docs/screenshot.png" alt="CompSim main window" width="800"></p>
-->

CompSim lets you build gas and two-phase process flowsheets by dragging unit
operations onto a canvas and wiring them together. It then runs them in time:
pressures, flows, levels and compositions change step by step, and you can
watch them on live trend charts. Simulation variables can also be exchanged
with real or virtual PLCs over **Modbus**, **OPC UA** or **OpenPLC**, which
makes CompSim usable for operator training, control-logic testing and virtual
commissioning.

---

## ✨ Features

- 🧩 **Node-based flowsheet editor.** Drag and drop blocks, connect ports,
  zoom and pan, and double-click a block to configure it.
- ⏱️ **Dynamic solver.** Explicit time-marching with a configurable time step
  (`dt`). Parameters can be changed while the simulation runs.
- 🧪 **Thermodynamics**
  - Equations of state: Ideal Gas, Peng-Robinson, Soave-Redlich-Kwong,
    Lee-Kesler and GERG-2008
  - Isothermal and EOS (φ-φ) flash with Rachford-Rice, and Raoult/Wilson
    K-values
  - Joule-Thomson cooling across throttling elements
  - Built-in component data: methane, ethane, propane, n-/i-butane,
    n-pentane, nitrogen, oxygen, water, hydrogen and air
- 📈 **Live trends.** Plot any process variable on configurable charts.
- 🔌 **PLC I/O.** Map AI, AO, DI and DO tags to simulation variables using
  Modbus TCP/RTU, OPC UA, OpenPLC Runtime or a built-in virtual backend.
- 💾 **Save and load flowsheets** as `.sim` files (JSON). Five examples are
  bundled.
- 🌗 **Light and dark themes.**

### Unit operations

| Block | Description |
|---|---|
| `StreamIn` | Source boundary: pressure, temperature, flow and composition |
| `StreamOut` | Sink boundary: sets the downstream back-pressure |
| `Valve` | Control valve sized to ISA-75.01 (compressible or liquid), with selectable characteristic |
| `CheckValve` | Non-return valve |
| `Vessel` | Two-phase capacity block (separator or receiver) with UV flash, level and hydrostatic head |
| `Mixer` | Adiabatic N-to-1 stream mixer |
| `Divider` | 1-to-N stream splitter with set fractions |
| `Compressor` | Variable-speed compressor driven by editable OEM performance curves (pressure ratio and efficiency) |
| `AnalogSource` | Analog signal source, for example a speed or valve-opening set-point |
| `AnalogSink` | Analog signal display |

---

## 📦 Installation

**Requirements:** Python 3.10 or newer, and a desktop environment that can
run Qt 6 applications.

<details open>
<summary><b>Option A: <code>uv</code> (recommended)</b></summary>

```bash
git clone https://github.com/mpicanco/CompSim.git
cd CompSim
uv sync
```

</details>

<details>
<summary><b>Option B: <code>pip</code> and a virtual environment</b></summary>

```bash
git clone https://github.com/mpicanco/CompSim.git
cd CompSim
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                 # or: pip install -r requirements.txt
```

</details>

<details>
<summary><b>Dependencies</b></summary>

| Package | Purpose |
|---|---|
| `PyQt6 >= 6.6` | GUI |
| `numpy >= 1.26`, `scipy >= 1.11` | Numerics and thermodynamics |
| `matplotlib >= 3.8` | Trend charts |
| `pymodbus >= 3.5` | Modbus and OpenPLC I/O (optional) |
| `asyncua >= 1.0` | OPC UA I/O (optional) |

</details>

### Running

```bash
uv run compsim       # with uv
compsim              # inside an activated virtual environment
python main.py       # directly from the source tree
```

---

## 🚀 Quick start

1. Start CompSim and open **File → Examples → 01 source valve sink**.
2. Click **Play** in the toolbar. The simulation clock starts in the status
   bar.
3. Double-click **Valve1** and change its *opening*. The flow responds
   immediately.
4. Open the **Trends** tab to watch the variables over time.
5. Use **Pause**, **Stop** and **Reset** to control the run, and change the
   **dt (s)** spin box to adjust the time step.

### Editor controls

| Action | How |
|---|---|
| Add a block | Drag it from the sidebar onto the canvas, or click it |
| Connect blocks | Drag from an output port to an input port |
| Configure a block | Double-click it |
| Delete a block or connection | Select it and press <kbd>Delete</kbd> |
| Zoom | Mouse wheel |
| Open / save | <kbd>Ctrl</kbd>+<kbd>O</kbd> / <kbd>Ctrl</kbd>+<kbd>S</kbd> |
| Close flowsheet | <kbd>Ctrl</kbd>+<kbd>W</kbd> |
| Switch theme | **Light/Dark** button in the toolbar |

### Bundled examples

| File | What it shows |
|---|---|
| [`01_source_valve_sink.sim`](examples/01_source_valve_sink.sim) | The simplest flowsheet: a source, a valve and a sink |
| [`02_vessel_fill_and_vent.sim`](examples/02_vessel_fill_and_vent.sim) | A receiver pressurising until inlet and vent flows balance |
| [`03_split_and_mix.sim`](examples/03_split_and_mix.sim) | Splitting a stream 40/60, throttling each branch and recombining it |
| [`04_compressor_receiver.sim`](examples/04_compressor_receiver.sim) | A variable-speed compressor charging a receiver through a check valve |
| [`05_integrated_plant.sim`](examples/05_integrated_plant.sim) | An integrated plant that uses every block type |

---

## 🔌 PLC integration

Open the **I/O OpenPLC** tab to connect the simulation to a controller:

1. Choose a backend: **Modbus TCP**, **Modbus RTU**, **OPC UA**,
   **OpenPLC** or **Virtual (demo)**.
2. Set the endpoint (host and port, serial port and baud rate, or OPC UA URL).
3. Add tags and bind each one to a simulation variable:

   | Signal | Direction | Data | Modbus register |
   |---|---|---|---|
   | **AI** | PLC → simulation | float | Input register |
   | **AO** | simulation → PLC | float | Holding register |
   | **DI** | PLC → simulation | bool | Discrete input |
   | **DO** | simulation → PLC | bool | Coil |

4. Start the simulation. Tags are exchanged every step.

The **OpenPLC** backend uses the default OpenPLC Runtime Modbus map. You can
enter addresses in OpenPLC notation (`%IX`, `%QX`, `%IW`, `%QW`, `%MW`, …)
and CompSim translates them to Modbus registers.

> [!TIP]
> Use **Virtual (demo)** to test tag mappings without any hardware. It echoes
> writes back as reads.

---

## 🐍 Using the core without the GUI

The simulation core (`core/`, `models/`) does not depend on Qt and can be
scripted directly:

```python
from core.controller import SimulationController
from models import create_block

sim = SimulationController(dt=1.0)

src   = sim.add_block(create_block("StreamIn",  "Supply"))
valve = sim.add_block(create_block("Valve",     "V1"))
sink  = sim.add_block(create_block("StreamOut", "Atm"))

sim.add_edge(src.outputs["out"],   valve.inputs["in"])
sim.add_edge(valve.outputs["out"], sink.inputs["in"])

for _ in range(100):
    sim.step()

print(f"t = {sim.simulator.time} s")
```

---

## 🗂️ Project structure

```
COMP_SIM/
├── main.py              # Application entry point
├── core/                # UI-independent simulation engine
│   ├── graph.py         #   Flowsheet graph (blocks + edges)
│   ├── solver.py        #   Dynamic time-stepping solver
│   ├── controller.py    #   Facade used by the GUI
│   ├── flow.py          #   ISA-75.01 flow equations
│   ├── data.py          #   Component property data
│   └── thermo/          #   EOS models, flash, Joule-Thomson, GERG-2008
├── models/              # Unit operation blocks
├── plcio/               # PLC I/O backends (Modbus, OPC UA, OpenPLC, virtual)
├── gui/                 # PyQt6 interface (canvas, trends, dialogs, I/O tab)
├── styles/              # Light and dark Qt stylesheets
└── examples/            # Bundled .sim flowsheets
```

<details>
<summary><b>📄 <code>.sim</code> file format</b></summary>

Flowsheets are stored as JSON with the following top-level keys:

| Key | Content |
|---|---|
| `format`, `version` | `"comp-sim-flowsheet"`, `1` |
| `description` | Free-text description |
| `dt` | Solver time step [s] |
| `blocks` | `name → {type, name, pos, config}` |
| `edges` | `[source_block, output_port, target_block, input_port]` |
| `charts` | Trend definitions: a list of `(block, variable_path, label)` pens |

> [!NOTE]
> All values are in **SI units** (Pa, K, kg/s, m³).

</details>

---

## 🤝 Contributing

Contributions are welcome. To add a new unit operation:

1. Create a class in [`models/`](models/) that subclasses `ProcessBlock` or
   `CapacityBlock` from [`core/base.py`](core/base.py), and set `block_type`
   and `category`.
2. Register it in `BLOCK_REGISTRY` in
   [`models/__init__.py`](models/__init__.py).

To add an equation of state, subclass `EquationOfState` in
[`core/thermo/`](core/thermo/) and add it to `EOS_REGISTRY` in
[`core/thermo/__init__.py`](core/thermo/__init__.py).

Typical workflow:

1. Fork the repository and create a branch: `git checkout -b feature/my-block`
2. Commit your changes with a clear message.
3. Open a pull request describing what changed and how you tested it.

---

## 📚 References

- ANSI/ISA-75.01.01: *Flow Equations for Sizing Control Valves*
- Kunz, O. & Wagner, W. (2012). *The GERG-2008 Wide-Range Equation of State
  for Natural Gases and Other Mixtures.* J. Chem. Eng. Data, 57(11).
- Lee, B. I. & Kesler, M. G. (1975). *A Generalized Thermodynamic Correlation
  Based on Three-Parameter Corresponding States.* AIChE J., 21(3).
- Peng, D.-Y. & Robinson, D. B. (1976). *A New Two-Constant Equation of
  State.* Ind. Eng. Chem. Fundam., 15(1).

---

## 📝 License

No license has been specified yet. Add a `LICENSE` file before publishing.
