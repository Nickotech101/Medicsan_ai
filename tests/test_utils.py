import os
import json
import pytest
from app import load_json, save_json, add_to_history, update_analytics, User, History, Analytics, db

def test_load_json_existing_file(tmp_path):
    # Create a temporary JSON file
    test_file = tmp_path / "test.json"
    data = {"key": "value"}
    test_file.write_text(json.dumps(data))
    
    # Test loading
    result = load_json(str(test_file), default={})
    assert result == data

def test_load_json_non_existing_file(tmp_path):
    # Test loading a non-existing file creates it with default
    test_file = tmp_path / "new_test.json"
    default_data = {"new": "default"}
    
    result = load_json(str(test_file), default=default_data)
    
    assert result == default_data
    assert test_file.exists()
    assert json.loads(test_file.read_text()) == default_data

def test_save_json(tmp_path):
    test_file = tmp_path / "save_test.json"
    data = {"save": "me"}
    
    save_json(str(test_file), data)
    
    assert test_file.exists()
    assert json.loads(test_file.read_text()) == data

def test_add_to_history(app, init_database, mocker):
    with app.test_request_context():
        # Create a mock user
        user = User(username="testuser", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        # Mock current_user
        mocker.patch('app.current_user', user)

        # Add history
        add_to_history("Paracetamol", "database")
        
        histories = db.session.query(History).all()
        assert len(histories) == 1
        assert histories[0].query == "Paracetamol"
        assert histories[0].source == "database"
        assert histories[0].user_id == user.id

def test_add_to_history_unauthenticated(app, init_database, mocker):
    with app.test_request_context():
        # Mock current_user as unauthenticated
        class MockAnonUser:
            is_authenticated = False
            
        mocker.patch('app.current_user', MockAnonUser())

        add_to_history("Paracetamol", "database")
        
        histories = db.session.query(History).all()
        assert len(histories) == 0

def test_update_analytics(app, init_database, mocker):
    with app.test_request_context():
        user = User(username="testuser", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        mocker.patch('app.current_user', user)

        # Update analytics first time
        update_analytics("Paracetamol")
        
        stats = db.session.query(Analytics).all()
        assert len(stats) == 1
        assert stats[0].query == "paracetamol"  # should be lowercased
        assert stats[0].count == 1

        # Update again, count should increment
        update_analytics("Paracetamol")
        
        stats = db.session.query(Analytics).all()
        assert len(stats) == 1
        assert stats[0].count == 2
