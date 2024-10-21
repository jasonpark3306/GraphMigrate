import requests
import os
from PIL import Image
from io import BytesIO

# You need to sign up for a free Unsplash API key
UNSPLASH_ACCESS_KEY = 'YOUR_UNSPLASH_API_KEY_HERE'

def download_profile_picture(username):
    # Unsplash API endpoint for random photos
    url = f'https://api.unsplash.com/photos/random?query=portrait&orientation=squarish&client_id={UNSPLASH_ACCESS_KEY}'

    try:
        # Get a random image URL from Unsplash
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        image_url = data['urls']['regular']

        # Download the image
        image_response = requests.get(image_url)
        image_response.raise_for_status()

        # Open the image and resize it
        img = Image.open(BytesIO(image_response.content))
        img = img.resize((200, 200))  # Resize to 200x200 pixels

        # Save the image
        filename = f'{username}.jpg'
        img.save(filename)
        print(f'Successfully downloaded and saved {filename}')

    except requests.RequestException as e:
        print(f'Error downloading image for {username}: {e}')

# List of usernames
usernames = [
    "Ali", "Amy", "Ben", "Cloe", "Jack", "Kate", "Soyer", "Tayler",
    "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason",
    "Wei", "Xia", "Yong", "Mei", "Jian", "Ling", "Hao", "Fang",
    # ... add all 100 names here ...
]

# Create a directory for the profile pictures
os.makedirs('profile_pictures', exist_ok=True)
os.chdir('profile_pictures')

# Download profile pictures for each username
for username in usernames:
    download_profile_picture(username)