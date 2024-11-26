import os
import json
import base64
import requests
from dotenv import load_dotenv
from typing import Optional, Dict, Any

def decode_jwt(token: str) -> str:
    """Decode a JWT token to extract user information."""
    base64_url = token.split(".")[1]
    base64_str = base64_url.replace("-", "+").replace("_", "/")
    padded_base64_str = base64_str + "=" * (4 - len(base64_str) % 4)
    
    decoded_bytes = base64.b64decode(padded_base64_str)
    return decoded_bytes.decode("utf-8")

def get_user_info(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate user with API key and get user information.
    Args:
        api_key (str): The user's API key from Playbook3D web editor
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing user email and credits if successful,
                                None if authentication fails
    """
    # Determine the path to the .env file
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    # Load the .env file
    load_dotenv(dotenv_path=env_path)

    try:
        # Get access token using API key
        alias_url = os.getenv("ALIAS_URL")
        jwt_request = requests.get(alias_url + api_key)
        if jwt_request.status_code != 200:
            print(f"Failed to get access token. Status code: {jwt_request.status_code}")
            return None

        access_token = jwt_request.json()["access_token"]
        
        # Decode JWT to get username
        decoded_jwt = decode_jwt(access_token)
        decoded_json = json.loads(decoded_jwt)
        username = decoded_json["username"]

        # Get user information using username and access token
        url = os.getenv("USER_URL").replace("*", username)
        headers = {
            "authorization": access_token,
            "x-api-key": os.getenv("X_API_KEY")
        }
        
        user_request = requests.get(url=url, headers=headers)
        if user_request.status_code != 200:
            print(f"Failed to get user info. Status code: {user_request.status_code}")
            return None

        user_data = user_request.json()
        return {
            "email": user_data["email"],
            "credits": user_data["users_tier"]["credits"]
        }

    except Exception as e:
        print(f"Authentication error: {str(e)}")
        return None

def validate_api_key(api_key: str) -> bool:
    """
    Validate if the provided API key has the correct format and can authenticate.
    Args:
        api_key (str): The API key to validate
    Returns:
        bool: True if the API key is valid, False otherwise
    """
    if not api_key or len(api_key) != 36:
        return False
    
    user_info = get_user_info(api_key)
    return user_info is not None
