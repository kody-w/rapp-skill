# Changelog

## 1.1.0

- Ship the exact `rapp-agent-converter` CAT Agent Skills submission as a
  second discoverable skill.
- Route all `agent.py ↔ Agent Skill` work through its bundled `toast.py`.
- Keep RAPP lifecycle operations in `rapp.py`; no duplicate converter is added.
- Verify converter selftest, sample roundtrip, linked-pair emission, and
  byte-exact restoration in the offline test suite.
