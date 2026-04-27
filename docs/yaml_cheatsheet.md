# YAML Cheat Sheet
## For Network Automation Inventory Files — NAMS26

---

### What YAML Is

YAML is a human-readable data format. In NAMS26 it is the **source of truth** — the
single file that describes what every device should look like. The Python scripts read
the YAML, pass it to the Jinja2 template, and render the IOS configuration.

**The golden rule:** If it's not in the YAML, it doesn't get configured.

---

### Basic Syntax Rules

```yaml
# This is a comment

key: value                    # String value
number: 100                   # Integer value
quoted: "100"                 # String that looks like a number — avoid this
boolean_true: true            # Boolean true
boolean_false: false          # Boolean false
empty: ""                     # Empty string
null_value: ~                 # Null / None
```

**Indentation is everything.** YAML uses spaces (never tabs) to show structure.
Two spaces per indent level is the NAMS26 standard.

---

### Strings

```yaml
description: "OOB Management"     # Quoted string — use for special characters
description: OOB Management       # Unquoted string — fine for simple values
description: ""                   # Empty string
description: ~                    # Null — means "not set"
```

**NAMS26 standard:** Use `""` for intentionally blank fields. Use `~` for null/absent.

---

### Integers vs Strings

```yaml
speed: 100          # Integer — correct NAMS26 standard for active Ethernet
speed: "100"        # String — WRONG in NAMS26 — causes type comparison issues
shutdown: true      # Boolean — not quoted
area: 0             # Integer — the falsy zero — handle carefully in Jinja2
```

---

### Nested Structure (Mappings)

```yaml
device:
  hostname: R1
  platform: ios
  ospf:
    process_id: 1
    router_id: 0.0.0.1
```

Access in Jinja2: `{{ device.ospf.router_id }}`

---

### Lists (Sequences)

```yaml
networks:
  - 192.168.1.0
  - 10.0.0.0
  - 172.16.0.0
```

Access in Jinja2:
```jinja2
{% for network in device.networks %}
 network {{ network }}
{% endfor %}
```

---

### List of Mappings

```yaml
interfaces:
  - name: Ethernet0/0
    ip: 192.1.12.1/24
    shutdown: false
  - name: Ethernet0/1
    ip: 192.1.13.1/24
    shutdown: false
```

---

### Mappings of Mappings (NAMS26 Pattern)

```yaml
interfaces:
  Ethernet0/0:
    description: "Link to R2"
    ipv4_address: 192.1.12.1/24
    shutdown: false
    speed: 100
    duplex: full
  Ethernet0/1:
    description: "Link to R3"
    ipv4_address: 192.1.13.1/24
    shutdown: false
    speed: 100
    duplex: full
  Ethernet1/3:
    description: "OOB Management"
    ipv4_address: 192.168.1.101/24
    shutdown: false
    speed: ""
    duplex: ""
```

Access in Jinja2: `{% for intf_name, intf in device.interfaces.items() %}`

---

### YAML Anchors and Aliases

Anchors define a reusable block. Aliases reference it. Used in NAMS26 for credentials.

```yaml
# Define the anchor
default_credentials: &creds
  username: netadmin
  password: admin

# Reference the anchor — copies the values
R1:
  hostname: r1.lab
  <<: *creds        # Merges username and password into R1

R2:
  hostname: r2.lab
  <<: *creds        # Same credentials, defined once
```

**Benefit:** Change credentials in one place, updates everywhere.

---

### Multi-line Strings

```yaml
# Literal block — preserves newlines (|)
banner: |
  Authorized users only.
  All activity is monitored.

# Folded block — newlines become spaces (>)
description: >
  This is a long description
  that wraps across lines.
```

---

### NAMS26 Device Structure Pattern

```yaml
devices:
  R1:
    hostname: r1.lab
    username: netadmin
    password: admin
    platform: ios
    oob_interface: Ethernet1/3

    interfaces:
      Ethernet0/0:
        description: "Link to R2"
        ipv4_address: 192.1.12.1/24
        shutdown: false
        speed: 100
        duplex: full

    ospf:
      process_id: 1
      router_id: 0.0.0.1
      networks:
        - prefix: 192.1.12.0/24
          area: 0

    eigrp: ~          # Null sentinel — this router has no EIGRP
```

---

### Common NAMS26 YAML Patterns

**Active Ethernet interface:**
```yaml
Ethernet0/0:
  description: "Link to R2"
  ipv4_address: 192.1.12.1/24
  shutdown: false
  speed: 100        # Unquoted integer
  duplex: full
```

**Unused Ethernet interface:**
```yaml
Ethernet1/0:
  description: "UNUSED"
  ipv4_address: ""
  shutdown: true
  speed: ""
  duplex: ""
```

**Loopback interface:**
```yaml
Loopback0:
  description: ""
  ipv4_address: 1.0.0.1/8
  shutdown: false
  speed: ""
  duplex: ""
```

**OOB interface (reference only — never rendered):**
```yaml
Ethernet1/3:
  description: "OOB Management"
  ipv4_address: 192.168.1.101/24
  shutdown: false
  speed: ""
  duplex: ""
```

---

### Enterprise Interface Variables (Extended Reference)

```yaml
Ethernet1/2:
  description: ""
  ip: ""
  shutdown: true
  speed: ""
  duplex: ""
  mtu: ""
  bandwidth: ""
  delay: ""
```

---

### Quick Troubleshooting

| Symptom | Likely Cause |
|---------|-------------|
| Template renders blank for a field | Value is `~` or `""` — check YAML |
| Area 0 interfaces not rendered | `ospf_area: 0` is falsy — use `is not none` guard in template |
| Speed/duplex rendered on Ethernet | Template guard missing — check `and 'Ethernet' not in intf_name` |
| Wrong IP mask rendered | `speed: "100"` quoted string — remove quotes |
| Credentials not found | Anchor `&creds` defined but alias `*creds` not applied |
| Indentation error on load | Mixed tabs and spaces — YAML requires spaces only |

---

*NAMS26 — YAML Cheat Sheet — docs/yaml_cheatsheet.md*
*Staged for integration into APPENDIX.md — Section 8*
