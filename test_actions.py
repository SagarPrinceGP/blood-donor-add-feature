import app

client = app.app.test_client()

# Login session
with client.session_transaction() as sess:
    sess["user"] = "sagar"
    sess["admin"] = True
    sess["role"] = "admin"

print("1. Testing adding a new donor...")
res = client.post("/add", data={
    "name": "Dr. Aarav Patel",
    "blood": "O-",
    "phone": "9876501234",
    "city": "Mysore",
    "age": "32",
    "gender": "Male",
    "status": "Available",
    "last_donated": "2026-01-15"
}, follow_redirects=True)
assert res.status_code == 200
assert b"Dr. Aarav Patel" in res.data
print("   -> Donor added successfully and appears in directory!")

# Get ID of the newly added donor
conn = app.get_db()
c = conn.cursor()
c.execute("SELECT id FROM donors WHERE phone='9876501234'")
donor_id = c.fetchone()["id"]
conn.close()

print(f"2. Testing editing donor #{donor_id}...")
res = client.post(f"/edit/{donor_id}", data={
    "name": "Dr. Aarav Patel (Updated)",
    "blood": "O-",
    "phone": "9876501234",
    "city": "Mysore",
    "age": "33",
    "gender": "Male",
    "status": "Available",
    "last_donated": "2026-02-01",
    "total_donations": "5"
}, follow_redirects=True)
assert res.status_code == 200
assert b"Dr. Aarav Patel (Updated)" in res.data
print("   -> Donor edited successfully!")

print(f"3. Testing deleting donor #{donor_id}...")
res = client.get(f"/delete/{donor_id}", follow_redirects=True)
assert res.status_code == 200
assert b"Donor deleted successfully" in res.data
print("   -> Donor deleted cleanly!")

print("4. Testing posting a new blood request...")
res = client.post("/requests/add", data={
    "patient_name": "Kavitha N",
    "blood_group": "AB-",
    "units": "2",
    "hospital": "Columbia Asia Hospital",
    "city": "Mysore",
    "contact_phone": "9988776655",
    "urgency": "Critical",
    "notes": "Emergency ICU admission"
}, follow_redirects=True)
assert res.status_code == 200
assert b"Kavitha N" in res.data
print("   -> Blood request posted and rendered!")

# Get ID of request
conn = app.get_db()
c = conn.cursor()
c.execute("SELECT id FROM blood_requests WHERE patient_name='Kavitha N'")
req_id = c.fetchone()["id"]
conn.close()

print(f"5. Testing marking request #{req_id} as Fulfilled...")
res = client.get(f"/requests/status/{req_id}/Fulfilled", follow_redirects=True)
assert res.status_code == 200
assert b"Fulfilled" in res.data
print("   -> Blood request status updated!")

print(f"6. Cleaning up test request #{req_id}...")
res = client.get(f"/requests/delete/{req_id}", follow_redirects=True)
assert res.status_code == 200
print("   -> Cleaned up test request!")

print("\nAll action lifecycle tests passed cleanly!")
