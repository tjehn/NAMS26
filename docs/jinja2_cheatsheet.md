# Jinja2 Cheat Sheet
## For Network Automation Templates — NAMS26

---

### The Four Core Concepts

| Syntax | Purpose | Example |
|--------|---------|---------|
| `{{ }}` | Insert a value | `{{ intf.description }}` |
| `{% %}` | Logic / control flow | `{% if %}` `{% for %}` |
| `{# #}` | Comment — not rendered | `{# This is a note #}` |
| `\|` | Apply a filter to a value | `{{ ip \| ipv4_addr }}` |

---

### Inserting Values

```jinja2
{{ variable }}
{{ device.hostname }}
{{ intf.description }}
{{ ospf.router_id }}
```
Inserts the value of the variable directly into the output.

---

### If / Else

```jinja2
{% if condition %}
  do this
{% endif %}

{% if condition %}
  do this
{% else %}
  do that
{% endif %}

{% if condition %}
  do this
{% elif other_condition %}
  do that
{% else %}
  do something else
{% endif %}
```

**Common conditions in NAMS26:**
```jinja2
{# Check value exists and is not blank #}
{% if intf.description and intf.description != "" %}

{# Check a boolean #}
{% if intf.shutdown %}

{# Check a value is not null #}
{% if intf.ospf_area is not none %}

{# The safe way to check ospf_area — 0 is falsy in Python/Jinja2 #}
{% if intf.ospf_area is not none and intf.ospf_area != "" %}

{# Check string equality #}
{% if device.platform == "ios" %}

{# Check value is not something #}
{% if intf_name != device.oob_interface %}
```

---

### For Loops

```jinja2
{% for item in list %}
  {{ item }}
{% endfor %}

{% for key, value in dictionary.items() %}
  {{ key }}: {{ value }}
{% endfor %}
```

**NAMS26 example — loop through interfaces:**
```jinja2
{% for intf_name, intf in device.interfaces.items() %}
interface {{ intf_name }}
{% endfor %}
```

**Loop with condition inside:**
```jinja2
{% for intf_name, intf in device.interfaces.items() %}
{% if intf_name != device.oob_interface %}
interface {{ intf_name }}
{% endif %}
{% endfor %}
```

**Loop variables:**
```jinja2
{{ loop.index }}     {# Current iteration — starts at 1 #}
{{ loop.index0 }}    {# Current iteration — starts at 0 #}
{{ loop.first }}     {# True on first iteration #}
{{ loop.last }}      {# True on last iteration #}
```

---

### Filters

Filters transform a value before it is inserted. Applied with the pipe `|` character.

**Built-in filters:**
```jinja2
{{ value | default("N/A") }}        {# Use default if value is undefined #}
{{ value | upper }}                  {# Convert to uppercase #}
{{ value | lower }}                  {# Convert to lowercase #}
{{ value | trim }}                   {# Remove leading/trailing whitespace #}
{{ list | join(", ") }}             {# Join list items with separator #}
{{ value | int }}                    {# Convert to integer #}
{{ value | string }}                 {# Convert to string #}
{{ list | length }}                  {# Count items in a list #}
```

**NAMS26 custom filters:**
```jinja2
{{ intf.ipv4_address | ipv4_addr }}       {# Extract address from CIDR: 10.0.0.1/24 → 10.0.0.1 #}
{{ intf.ipv4_address | ipv4_mask }}       {# Extract mask from CIDR:    10.0.0.1/24 → 255.255.255.0 #}
{{ intf.ipv4_address | cidr_to_netmask }} {# NAPALM modules equivalent #}
```

---

### Tests

Tests check a condition about a value. Used with `is`.

```jinja2
{% if value is defined %}      {# Value exists in the data #}
{% if value is none %}         {# Value is null/None #}
{% if value is not none %}     {# Value is not null #}
{% if value is string %}       {# Value is a string #}
{% if value is number %}       {# Value is a number #}
{% if list is iterable %}      {# Value can be looped over #}
```

---

### Whitespace Control

Jinja2 renders newlines around block tags. Use `-` to strip whitespace:

```jinja2
{%- if condition %}    {# Strip whitespace BEFORE this tag #}
{% if condition -%}    {# Strip whitespace AFTER this tag #}
{%- if condition -%}   {# Strip whitespace on both sides #}
```

---

### Comments

```jinja2
{# This is a comment — it does not appear in the rendered output #}
```

---

### Undefined / Default Values

```jinja2
{{ variable | default("fallback") }}
{{ variable | default("", true) }}   {# Use default for both undefined AND falsy values #}
```

---

### The NAMS26 Falsy Zero Problem

```jinja2
{# WRONG — ospf_area: 0 is falsy, this block is skipped for Area 0 #}
{% if intf.ospf_area %}
 ip ospf {{ intf.ospf_area }} area {{ intf.ospf_area }}
{% endif %}

{# CORRECT — explicitly checks for None and empty string #}
{% if intf.ospf_area is not none and intf.ospf_area != "" %}
 ip ospf {{ intf.ospf_area }} area {{ intf.ospf_area }}
{% endif %}
```

---

### Quick Reference — Block Structure

```jinja2
{% for intf_name, intf in device.interfaces.items() %}   {# Open loop #}
{% if intf_name != device.oob_interface %}               {# Open condition #}
interface {{ intf_name }}                                {# Insert value #}
{% if intf.description and intf.description != "" %}     {# Nested condition #}
 description {{ intf.description }}
{% endif %}                                              {# Close nested condition #}
!
{% endif %}                                              {# Close outer condition #}
{% endfor %}                                             {# Close loop #}
```

**Rule:** Every `{% if %}` needs an `{% endif %}`. Every `{% for %}` needs an `{% endfor %}`.

---

*NAMS26 — Jinja2 Cheat Sheet — docs/jinja2_cheatsheet.md*
*Staged for integration into APPENDIX.md — Section 7*
