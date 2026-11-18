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
    n-pentane, nitrogen, oxygen, carbon dioxide, water, hydrogen, hydrogen
    sulfide and air; GERG-2008 covers all 21 natural-gas components
  - See [Thermodynamics](#-thermodynamics-equations-of-state-and-gas-composition)
    for EOS choice, composition entry, air and natural gas
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

## 🧪 Thermodynamics: equations of state and gas composition

### Where the EOS is chosen

A stream carries **pressure, temperature, mass flow, phase and composition**,
but **not** an equation of state. Each block that needs gas properties has its
own `eos` parameter (a drop-down in its config panel) and applies that model
to the stream it receives. Choose the same EOS in every block of a flowsheet
unless you have a reason not to.

| Block | What its EOS is used for |
|---|---|
| `Valve` | Inlet compressibility *Z* and molar mass in the ISA-75.01 gas flow equation; Joule-Thomson temperature drop |
| `Vessel` | Gas molar volume (pressure from hold-up), and the phase split when `flash_method = "eos"` |
| `Mixer` | Molar mass of each inlet, to blend mole fractions on a **molar-flow** basis |
| `Compressor` | No selector: inlet density is always ideal gas (for the volumetric flow read on the curves) |
| `StreamIn` | `eos` is stored but informational only; downstream blocks use their own |

### Available equations of state

| EOS | Model | Best for | Components it knows |
|---|---|---|---|
| **Ideal Gas** | *Z* = 1 | Low pressure, quick runs | Any name (only the molar mass is needed) |
| **Peng-Robinson** | Cubic, *k<sub>ij</sub>* = 0 | General hydrocarbon gas; rigorous φ-φ flash in a `Vessel` | Built-in property list (below) |
| **Soave-Redlich-Kwong** | Cubic, *k<sub>ij</sub>* = 0 | As Peng-Robinson | Built-in property list |
| **Lee-Kesler** | Corresponding states, pseudo-critical mixing | Non-polar gas mixtures | Built-in property list |
| **GERG-2008** | Multi-parameter Helmholtz (ISO 20765-2) | Natural gas and fiscal-quality accuracy | The 21 GERG components (below) |

Notes:

- The cubic models use no binary interaction parameters (*k<sub>ij</sub>* = 0),
  so they are approximate for mixtures with CO₂, H₂S, water or hydrogen.
- GERG-2008 returns the **vapour** root. If no vapour root exists at (*P*, *T*)
  it falls back to *Z* = 1 rather than stopping the simulation.
- The `Vessel` rigorous flash (`flash_method = "eos"`) needs a cubic EOS. With
  any other EOS, or if it fails to converge, it falls back to Wilson K-values.

### Component names

Names are **lower case and must be spelled exactly** as below.

| Component | Name to type | Built-in data (cubic, Lee-Kesler, flash, J-T) | GERG-2008 |
|---|---|:---:|:---:|
| Methane | `methane` | ✅ | ✅ |
| Nitrogen | `nitrogen` | ✅ | ✅ |
| Carbon dioxide | `carbon dioxide` | ✅ | ✅ |
| Ethane | `ethane` | ✅ | ✅ |
| Propane | `propane` | ✅ | ✅ |
| n-Butane | `n-butane` | ✅ | ✅ |
| Isobutane | `i-butane` | ✅ | ✅ |
| n-Pentane | `n-pentane` | ✅ | ✅ |
| Isopentane | `i-pentane` | — | ✅ |
| n-Hexane … n-Decane | `n-hexane`, `n-heptane`, `n-octane`, `n-nonane`, `n-decane` | — | ✅ |
| Hydrogen | `hydrogen` | ✅ | ✅ |
| Oxygen | `oxygen` | ✅ | ✅ |
| Carbon monoxide | `carbon monoxide` | — | ✅ |
| Water | `water` | ✅ | ✅ |
| Hydrogen sulfide | `hydrogen sulfide` | ✅ | ✅ |
| Helium | `helium` | — | ✅ |
| Argon | `argon` | — | ✅ |
| Air (pseudo-component) | `air` | ✅ | ❌ |

Names are matched case-insensitively and extra spaces are ignored
(`Carbon  Dioxide` → `carbon dioxide`). **Any other name is rejected** on
Apply, and the closest valid name is suggested: `co2` → *"unknown component
'co2'. Did you mean 'carbon dioxide'?"*, and the same for `h2s`, `n2`, `ic4`,
typos such as `metane`, and so on. A component listed twice is also rejected.

> [!WARNING]
> The components marked "—" in the built-in data column are valid names but
> are fully modelled **only by GERG-2008**. Ideal Gas, the cubic EOS,
> Lee-Kesler, the flash, the Joule-Thomson estimate and the `Mixer` give them
> **air-like** properties (*M* = 28.964 g/mol, *T*<sub>c</sub> = 132.6 K,
> *P*<sub>c</sub> = 37.71 bar, ω = 0). Use `i-pentane`, `n-hexane`+,
> `carbon monoxide`, `helium` and `argon` only when every block of the
> flowsheet uses GERG-2008. Conversely, GERG-2008 raises an error for `air`;
> the simulation then **pauses** and shows the message in the status bar.
>
> The check applies to entries made in the config panels. Compositions in a
> `.sim` file edited by hand are not validated when the file is loaded.

### Setting a composition

A composition is a mole-fraction dictionary `{'component': fraction, ...}`,
for example:

```python
{'methane': 0.9, 'ethane': 0.07, 'nitrogen': 0.03}
```

It is entered in three places:

| Where | Parameter | Meaning |
|---|---|---|
| `StreamIn` | `composition` | Composition of the feed |
| `Vessel` | `initial_composition` | Hold-up composition at *t* = 0 |
| `Compressor` | *Curve design conditions* → gas composition | Gas the performance curves refer to (reference only; it does not change the stream) |

On **Apply** / **OK** the entry is checked:

1. **Names must be known components** (see the table above); unknown names
   are rejected with a suggestion.
2. **Components not listed are 0.** Type only the components that are present.
3. **Fractions must be non-negative** and not all zero.
4. **The total must be 1** (tolerance 10⁻⁶). If it is not, for example when
   you type percentages `{'methane': 90, 'ethane': 10}`, a dialog shows the
   total and asks whether to **normalise**. *Yes* scales the fractions to sum
   to 1 and applies them. *No* applies nothing, keeps the dialog open and
   shows the error.
5. The composition is stored and shown in the **GERG-2008 / ISO 20765-2
   component order** (the order of the table above). Names outside that list,
   such as `air`, come last, alphabetically. AGA-8 uses the same 21
   components, with each isomer pair (butanes, pentanes) in the opposite order.

### How composition travels between blocks

Each block passes on a **copy** of the stream, so blocks never share a
composition object.

| Block | Effect on composition |
|---|---|
| `StreamIn` | Sets it from `composition` |
| `Valve`, `CheckValve`, `Compressor` | Unchanged |
| `Divider` | Unchanged; every branch gets the inlet composition and only the flow is split |
| `Mixer` | Blends the inlets on a molar-flow basis: *z<sub>i</sub>* = Σ (*ṁ<sub>k</sub>* / *M<sub>k</sub>*) *z<sub>i,k</sub>* / Σ (*ṁ<sub>k</sub>* / *M<sub>k</sub>*), with *M<sub>k</sub>* from the Mixer's EOS |
| `Vessel` | Integrates the component mole balance of the hold-up, flashes it, and sends the vapour composition *y* out of `vap_out` and the liquid composition *x* out of `liq_out` |

The **Live values** box of every config panel lists the stream compositions:
each material inlet; each outlet as well for blocks that can change the
composition (`Mixer`, `Vessel`, and `StreamIn`, which has no inlet); and the
`Vessel` hold-up composition. "—" means no flow of that phase, for example
`liq_out` while nothing has condensed.

### Special cases

#### Air

There is no air preset. Air can be entered in two ways:

| Entry | Use it when | Limitations |
|---|---|---|
| `{'air': 1.0}` | Plain air with Ideal Gas, Peng-Robinson, SRK or Lee-Kesler | A single pseudo-component: **not accepted by GERG-2008**; its oxygen/nitrogen content is not tracked through a `Mixer` or `Vessel` |
| `{'nitrogen': 0.79, 'oxygen': 0.21}` | Any EOS, and whenever air is mixed with other gases | — |
| `{'nitrogen': 0.7809, 'oxygen': 0.2095, 'argon': 0.0093, 'carbon dioxide': 0.0003}` | Dry-air accuracy with GERG-2008 | Argon has no built-in data, so use GERG-2008 in every block |

The bundled examples use `{'nitrogen': 0.79, 'oxygen': 0.21}`. Air does not
condense at practical conditions, so a `Vessel` holding air keeps an empty
`liq_out`.

#### Natural gas

There is no natural-gas preset either: enter the gas analysis directly, for
example a lean pipeline gas:

```python
{'methane': 0.90, 'nitrogen': 0.02, 'carbon dioxide': 0.01,
 'ethane': 0.05, 'propane': 0.015, 'n-butane': 0.0025, 'i-butane': 0.0025}
```

- **GERG-2008** is the reference EOS for natural gas (ISO 20765-2, the basis
  of AGA-8) and covers every component of a normal analysis, including
  `i-pentane`, `n-hexane` to `n-decane`, `helium` and `carbon monoxide`.
- With the **cubic EOS or Lee-Kesler**, components without built-in data are
  air-like (see the warning above). Lump the C₆+ fraction into `n-pentane`,
  and add `i-pentane` to `n-pentane`, rather than entering them separately.
- A dry, sweet gas behaves almost ideally at low pressure; use a real-gas EOS
  above a few bar.

#### Wet gas and condensation

`water` and the heavier hydrocarbons can condense in a `Vessel`. The phase split
depends on `flash_method`:

| `flash_method` | Model | Notes |
|---|---|---|
| `wilson` (default) | Wilson K-values from *T*<sub>c</sub>, *P*<sub>c</sub>, ω | Fast; rough for water |
| `raoult` | Antoine vapour pressure / *P* | Better for water and other condensables |
| `eos` | Rigorous φ-φ flash | Needs Peng-Robinson or SRK in the `Vessel` |

The condensate leaves through `liq_out` with its own composition *x*, so the
gas from `vap_out` is leaner in the condensable components than the feed.

#### Pure gases and other mixtures

A pure gas is a one-entry dictionary, e.g. `{'methane': 1.0}` (the
`StreamIn` default) or `{'hydrogen': 1.0}`. For hydrogen-rich or CO₂-rich
streams, prefer GERG-2008: the cubic EOS have no *k<sub>ij</sub>* and are least
accurate there.

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
- ISO 20765-2:2015: *Natural gas — Calculation of thermodynamic properties —
  Part 2: Single-phase properties (gas, liquid, and dense fluid) for extended
  ranges of application* (GERG-2008).
- AGA Report No. 8: *Thermodynamic Properties of Natural Gas and Related
  Gases* (2017, Part 1 DETAIL / Part 2 GERG-2008).
- Peng, D.-Y. & Robinson, D. B. (1976). *A New Two-Constant Equation of
  State.* Ind. Eng. Chem. Fundam., 15(1).

---

## 📝 License

No license has been specified yet. Add a `LICENSE` file before publishing.
