import app

client = app.app.test_client()

print("1. Testing /login (unauthenticated)...")
res = client.get("/login")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert b"Sign In to Dashboard" in res.data
print("   -> /login OK")

print("2. Testing /register (unauthenticated)...")
res = client.get("/register")
assert res.status_code == 200
assert b"Create Account" in res.data
print("   -> /register OK")

print("3. Testing /forgot...")
res = client.get("/forgot")
assert res.status_code == 200
assert b"Password Recovery" in res.data
print("   -> /forgot OK")

# Simulate login session
with client.session_transaction() as sess:
    sess["user"] = "sagar"
    sess["admin"] = True
    sess["role"] = "admin"

print("4. Testing / (Dashboard)...")
res = client.get("/")
assert res.status_code == 200
assert b"Welcome back, sagar!" in res.data
assert b"Total Donors Registered" in res.data
print("   -> / (Dashboard) OK")

print("5. Testing /donors (Directory)...")
res = client.get("/donors")
assert res.status_code == 200
assert b"Blood Donors Directory" in res.data
assert b"WhatsApp" in res.data
print("   -> /donors OK")

print("6. Testing /donors with filter ?blood=O+...")
res = client.get("/donors?blood=O%2B")
assert res.status_code == 200
assert b"punithkumar s" in res.data
print("   -> /donors filter OK")

print("7. Testing /add_donor...")
res = client.get("/add_donor")
assert res.status_code == 200
assert b"Register New Blood Donor" in res.data
print("   -> /add_donor OK")

print("8. Testing /requests...")
res = client.get("/requests")
assert res.status_code == 200
assert b"Emergency &amp; Urgent Blood Requests" in res.data or b"Emergency & Urgent Blood Requests" in res.data
print("   -> /requests OK")

print("9. Testing /compatibility...")
res = client.get("/compatibility?blood=O%2B")
assert res.status_code == 200
assert b"Smart Blood Compatibility &amp; Matcher" in res.data or b"Smart Blood Compatibility & Matcher" in res.data
print("   -> /compatibility OK")

print("10. Testing /export_csv...")
res = client.get("/export_csv")
assert res.status_code == 200
assert res.content_type == "text/csv; charset=utf-8"
assert b"Donor ID,Full Name,Blood Group" in res.data
print("   -> /export_csv OK")

print("11. Testing /api/compatibility/A+...")
res = client.get("/api/compatibility/A+")
assert res.status_code == 200
assert b"can_receive" in res.data
print("   -> /api/compatibility OK")

print("\nAll 11 Route and Template Integration Tests Passed Successfully!")
