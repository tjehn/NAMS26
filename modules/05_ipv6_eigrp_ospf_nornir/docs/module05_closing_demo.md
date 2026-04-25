# Module 05 Closing Demo — IPv6 EIGRP/OSPFv3

## Status
PLACEHOLDER — complete when scripts are implemented

## Planned Fault Injection Scenarios

### Scenario A — EIGRP→OSPF redistribution removed on R1

```bash
# 1. Inject fault — remove EIGRP→OSPF redistribution on R1
python utils/push_config.py --router R1 \
  --cmd "ipv6 router eigrp 100" "no redistribute ospf 1 metric 10000 100 255 1 1500"

# 2. Troubleshooter passes (neighbors still up — process-level fault)
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R1 --check neighbors

# 3. Verifier catches missing EIGRP routes on OSPF routers
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution

# 4. Restore correct config
python scripts/configure_ipv6_eigrp_ospf.py --router R1

# 5. Confirm verifier passes clean
python scripts/verify_ipv6_eigrp_ospf.py --router R1
```

### Scenario B — OSPF→EIGRP redistribution removed on R6

```bash
python utils/push_config.py --router R6 \
  --cmd "ipv6 router ospf 1" "no redistribute eigrp 111"
python scripts/troubleshoot_ipv6_eigrp_ospf.py --router R6 --check process
python scripts/verify_ipv6_eigrp_ospf.py --check redistribution
python scripts/configure_ipv6_eigrp_ospf.py --router R6
python scripts/verify_ipv6_eigrp_ospf.py --router R6
```
