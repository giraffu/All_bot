import requests

def test():
    # Login
    res = requests.post("http://localhost:8043/api/auth/login", data={"username": "chuzeyu", "password": "your_actual_password_or_we_can_just_use_dashboard_admin"})
    print(res.status_code, res.text)

test()
