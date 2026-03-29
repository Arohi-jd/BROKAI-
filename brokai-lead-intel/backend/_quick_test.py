import io
import pandas as pd
import httpx

buf = io.BytesIO()
pd.DataFrame([{"Company Name": "Haldiram's", "Location": "Delhi"}]).to_excel(buf, index=False)
buf.seek(0)
files = {"file": ("test.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
response = httpx.post("http://127.0.0.1:8000/process", files=files, timeout=120)
print("status", response.status_code)
body = response.json()
print("total", body.get("total"))
print("company", body.get("results", [{}])[0].get("company_name"))
print("error", (body.get("results", [{}])[0].get("error") or "")[:180])
