---
name: python-cli-sop
description: SOP for building macOS/Linux Python CLI tools — phased development, safety-first architecture, and project delivery. Use when starting a new Python CLI project or tool.
---

# Python CLI Tool Development SOP

A phased development methodology distilled from the VibeNet Control project. Applicable to any Python CLI tool, especially those dealing with system-level operations (networking, file I/O, process management).

---

## Phase 0: Environment Baseline

Before writing any code, verify the runtime environment.

### Checklist
```bash
python3 --version          # Confirm 3.9+
pip3 list | grep <library> # Check key dependencies
which <system-tool>        # Verify system tools (nmap, ffmpeg, etc.)
```

### Actions
- Create `requirements.txt` with pinned minimum versions
- If system tools are needed, note their install commands (brew, apt, etc.)
- **Test permission requirements early** — many system tools need sudo, and that changes the testing workflow

### Output
- `requirements.txt`
- Confirmed Python version and dependency list
- Permission model documented (what needs sudo, what doesn't)

---

## Phase 1: Core Module Skeleton

Build the project in vertical slices — one module at a time, each independently testable.

### Directory Convention
```
project/
├── main.py              # CLI entry point
├── core/
│   ├── __init__.py
│   └── <primary_module>.py
├── utils/
│   ├── __init__.py
│   └── <helper>.py
├── requirements.txt
└── CLAUDE.md
```

### Principles
1. **One module, one responsibility**: scanner → discovery, spoofing → MITM, config → sysctl. Never mix concerns.
2. **Each module is self-testable**: every `.py` file has a `main()` that exercises its own logic independently.
3. **No premature CLI**: don't wire modules together until each one works standalone.
4. **Discover before you invent**: check what the system already provides (nmap's OUI database, scapy's routing table, macOS sysctl) before building your own.

### Testing in Sandbox Constraints
When `sudo` or TTY is required but the sandbox can't provide it:

```
┌─────────────────────────────────────────────────────┐
│  Sandbox (Claude)           │  User Terminal         │
│                             │                        │
│  • Write code               │  • sudo python3 test   │
│  • Verify syntax & imports  │  • Report output       │
│  • Test pure functions      │  • Confirm behavior    │
│  • Inspect system state     │                        │
└─────────────────────────────────────────────────────┘
```

- **Sandbox**: write, syntax-check, test all pure/computational parts, inspect read-only system state
- **User terminal**: run privileged commands, paste output back for analysis

---

## Phase 2: Safe-by-Default Architecture

For any tool that mutates system state, implement a three-layer safety net.

### Three-Layer Safety Pattern

```python
# Layer 1: Permission gate — early exit if requirements not met
def main():
    if os.geteuid() != 0:
        print("Need sudo")
        sys.exit(1)

    resource = None
    try:
        # Layer 2: Main logic
        resource = DangerousOperation()
        resource.start()
        interactive_loop()

    except KeyboardInterrupt:
        # Layer 3: Explicit interrupt handling
        print("Interrupted — cleaning up...")

    finally:
        # Layer 3 (continued): GUARANTEED cleanup
        if resource is not None:
            resource.cleanup()
```

| Layer | Mechanism | Guards Against |
|-------|-----------|---------------|
| 1. Permission gate | `os.geteuid()`, capability checks | Running without required privileges |
| 2. Except handler | `except KeyboardInterrupt` | User Ctrl+C during I/O |
| 3. Finally block | `finally: cleanup()` | **Any** exit path — unhandled exceptions, sys.exit(), normal return |

**Rule**: `finally` must be the sole place where cleanup is called. Never call cleanup in both an except block AND finally — it leads to double-cleanup bugs.

### Context Manager for Reusable Safety

```python
class DangerousResource:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.cleanup()
        return False  # don't suppress exceptions
```

---

## Phase 3: CLI Integration

### Pattern: Scan → Select → Act Loop

```
1. Display options (scan results, numbered list)
2. User selects by number
3. Confirm selection
4. Enter action loop (k = kill, u = unkill, q = quit, Ctrl+C = emergency)
5. Cleanup on exit
```

### CLI Design Rules
- **Numbers, not names**: selecting `2` is faster and less error-prone than typing `192.168.1.100`
- **Single-letter commands**: `k`/`u`/`q` are faster to type than full words in a control loop
- **Default safe action**: if user presses Enter with no input, do nothing (not the most dangerous option)
- **Immediate feedback**: every action prints what it did (`"KILL SWITCH: 192.168.1.5 is now cut off"`)

### Signal Handling for Long-Running Processes

For background threads:
```python
class LoopingTask:
    def __init__(self):
        self._stop = threading.Event()

    def _loop(self):
        while not self._stop.is_set():
            self.do_work()
            self._stop.wait(interval)  # NOT time.sleep() — it's uninterruptible

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
```

Always use `Event.wait()` instead of `time.sleep()` in loops — it allows immediate interruption.

---

## Phase 4: Bug Hunting Playbook

Common bugs and their diagnostic approach:

### Foreign Data Format Mismatch

**Symptom**: Lookups/parsing returning "Unknown" or None for data that clearly exists.

**Diagnosis**:
```bash
# Inspect the source data directly — don't trust documentation
head -20 /path/to/data_file
```

**Root cause**: Format assumptions. nmap stores MACs as `AABBCC`, scapy provides `AA:BB:CC`. Always inspect raw source data, never assume format compatibility.

### Route Table / System API Encoding

**Symptom**: System API returns integers where you expect strings (e.g., `3232238080` for `192.168.10.0`).

**Root cause**: Kernels and low-level libraries often encode network addresses as `uint32` for efficiency.

**Fix**: Check if the data is human-readable before trying string operations. If it's in integer form, use `socket.inet_ntoa(struct.pack('!I', value))` to convert. Or use higher-level system commands as a fallback (`route get default` on macOS).

### Permission Testing Deadlock

**Symptom**: Can't test privileged code because sandbox has no TTY.

**Fix**: Establish a clear split-test workflow — sandbox tests pure logic, user terminal tests privileged operations. See Phase 1 testing diagram.

---

## Phase 5: Project Delivery

### Deliverable Checklist

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | End user | Features, install, usage, safety notes |
| `DEVELOPMENT_LOG.md` | Next developer | Architecture, design decisions, bugs & fixes, future roadmap |
| `run.sh` | End user | One-click dependency check + launch |
| `requirements.txt` | Build system | Reproducible environment |
| Updated `CLAUDE.md` | AI assistant | Current project state and technical decisions |

### README.md Template
1. One-sentence elevator pitch
2. Feature list (bullets)
3. Requirements table (component / version / purpose)
4. Installation (A: one-click, B: manual)
5. Usage (quick start + step-by-step with example output)
6. How it works (simple diagram + explanation for non-technical users)
7. Safety notes (limitations, warnings, intended use)

### DEVELOPMENT_LOG.md Template
1. Project overview (1 paragraph)
2. Core architecture (data flow diagram, mechanism explanations)
3. Key design decisions (each with: chosen approach, alternative, trade-off)
4. Bugs encountered (each with: symptom, root cause, fix)
5. Project structure (file tree with one-line descriptions)
6. Testing matrix (what was tested, how, status)
7. Future improvements (ranked by impact)

### run.sh Template
```bash
#!/usr/bin/env bash
set -e

# 1. Check each dependency
# 2. Auto-install what's missing (only via safe methods: pip, brew)
# 3. Report unfixable gaps
# 4. exec sudo python3 main.py
```

---

## Principles Summary

1. **Vertical slices**: Build and test one complete module before starting the next.
2. **Safe by default**: `finally` block is the single source of cleanup truth.
3. **Inspect, don't assume**: Always `head` foreign data sources before writing parsers.
4. **Sandbox + Terminal split**: Accept that privileged code can't be tested in the sandbox; design your workflow around it.
5. **Deliver for two audiences**: End users (README) and future developers (DEVELOPMENT_LOG).
