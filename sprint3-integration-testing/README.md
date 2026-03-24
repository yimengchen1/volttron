# Sprint 3: Integration Testing
## Home Assistant Driver — Extended Device Support

This folder contains Sprint 3 deliverables for integration testing the Home Assistant VOLTTRON driver.

## Files
- `test_integration_home_assistant.py` — Integration test suite (40 tests, 0 failures)
- `Sprint3_Integration_Testing_Report.docx` — Full report with test plan, results, and code examples
- `README.md` — This file

## How to Run

```bash
pip install requests-mock
cd sprint3-integration-testing
python test_integration_home_assistant.py
```

Expected output:
```
Ran 40 tests in 0.034s

OK
```

## What's Different from Sprint 2 Unit Tests

| Aspect | Unit Tests (Sprint 2) | Integration Tests (Sprint 3) |
|--------|----------------------|------------------------------|
| Mock boundary | Driver methods | HTTP transport (`requests`) |
| URL correctness | Not tested | ✅ Verified |
| Payload correctness | Not tested | ✅ JSON body inspected |
| Auth headers | Not tested | ✅ Bearer token verified |
| Error handling (HTTP) | Not tested | ✅ 500, 401, 404, connection |
| Round-trip write→read | Not tested | ✅ 3 scenarios |
| Multi-device scrape | Not tested | ✅ 8 points, 5 entities |

## Test Classes (8 classes, 40 tests)

1. **TestWritePathIntegration** (14) — Full write chain for all 5 device types
2. **TestReadPathIntegration** (9) — Full read chain via `_scrape_all()` + HTTP GET
3. **TestRoundTrip** (3) — Write then verify scrape reads correct value
4. **TestMultiDeviceScrape** (1) — Multiple devices in one `_scrape_all()` call
5. **TestAPIErrorHandling** (5) — HA returns 500, 404, connection errors
6. **TestConfigureIntegration** (3) — `configure()` with registry CSV data
7. **TestAuthHeaders** (3) — Bearer token present on every request
8. **TestGetPoint** (3) — `get_point()` reads single entity via HTTP

## Note
The integration tests import the driver from `../sprint2-ha-driver-extension/home_assistant.py`. No changes were made to the driver code.
