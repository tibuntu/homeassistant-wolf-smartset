# Test fixtures

- `description_heatpump.json`: `GetGuiDescriptionForGateway` response of a Wolf CHA heat pump with BM-2, MM1 and ISM. Source: `parameters-examples/heatpumpparameter.json` of [wolf-comm](https://github.com/janrothkegel/wolf-comm) (Apache-2.0, Copyright Jan Rothkegel and contributors), redacted with `scripts/record_fixtures.py` (serial number and manufacturing date blanked).
- `real/`: responses of the owner's installation, recorded and redacted with `scripts/record_fixtures.py`. System and gateway IDs are replaced by 1234 and 5678.
