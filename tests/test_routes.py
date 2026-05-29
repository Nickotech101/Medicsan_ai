from app import User


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_register_get(client):
    response = client.get("/register")
    assert response.status_code == 200


def test_register_post(client, init_database):
    response = client.post(
        "/register", data={"username": "newuser", "password": "password123"}, follow_redirects=True
    )

    assert response.status_code == 200
    # Check if user was created
    user = User.query.filter_by(username="newuser").first()
    assert user is not None


def test_login_get(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_post(client, init_database):
    # Register first
    client.post("/register", data={"username": "loginuser", "password": "password123"})

    # Then login
    response = client.post(
        "/login", data={"username": "loginuser", "password": "password123"}, follow_redirects=True
    )

    assert response.status_code == 200
    # Should redirect to home or dashboard, status 200 after redirect


def test_dashboard_unauthenticated(client):
    # /dashboard is @login_required
    response = client.get("/dashboard", follow_redirects=True)
    # Should redirect to login, let's just check it doesn't give 200 on dashboard
    # Wait, flask-login redirects to login view, which returns 200 if follow_redirects=True
    # But the URL will end in /login
    assert len(response.history) > 0
    assert response.history[0].status_code in [301, 302]
    assert "/login" in response.request.path


def test_api_suggestions(client, mocker):
    # Mock requests.get for FDA API if we don't want external calls
    # Or just rely on local cache since POPULAR_MEDICINES has Paracetamol
    response = client.get("/api/suggestions?q=para")
    assert response.status_code == 200

    data = response.get_json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)
    assert any(s.lower().startswith("para") for s in data["suggestions"])


def test_api_medicine_unauthenticated(client):
    # /api/medicine now requires login; unauthenticated requests must be redirected.
    response = client.post("/api/medicine", json={"medicine": "paracetamol"})
    assert response.status_code in (302, 401)


def test_api_medicine_no_data(logged_in_client):
    # Authenticated request with an empty body must still return 400.
    response = logged_in_client.post("/api/medicine", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_api_medicine_with_data(logged_in_client, mocker):
    mocker.patch("app.update_analytics")
    mocker.patch("app.add_to_history")

    mocker.patch.dict("app.MED_DB", {"testmed": {"generic_name": "Test Generic", "use": "Testing"}})

    response = logged_in_client.post("/api/medicine", json={"medicine": "testmed"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["source"] == "database"
    assert data["data"]["generic_name"] == "Test Generic"
