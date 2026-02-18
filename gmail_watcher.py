import os
import logging
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import yaml

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Globals
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
PROCESSED_IDS_FILE = 'processed_ids.txt'
NEEDS_ACTION_DIR = 'd:/hackathon0/hackathon/AI_Employee_Vault/Needs_Action'

# Ensure the Needs_Action directory exists
os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)

def load_processed_ids():
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    with open(PROCESSED_IDS_FILE, 'r') as f:
        return set(f.read().splitlines())

def save_processed_id(email_id):
    with open(PROCESSED_IDS_FILE, 'a') as f:
        f.write(email_id + '\n')

def create_markdown_file(email_data):
    file_name = f"{email_data['id']}.md"
    file_path = os.path.join(NEEDS_ACTION_DIR, file_name)
    
    yaml_frontmatter = {
        'type': 'email',
        'from': email_data['from'],
        'subject': email_data['subject'],
        'priority': 'high'
    }

    content = f"---\n{yaml.dump(yaml_frontmatter)}---\n\n{email_data['snippet']}"

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    logging.info(f"Created markdown file: {file_path}")

def fetch_unread_emails():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    service = build('gmail', 'v1', credentials=creds)

    results = service.users().messages().list(userId='me', labelIds=['UNREAD', 'IMPORTANT'], maxResults=10).execute()
    messages = results.get('messages', [])

    processed_ids = load_processed_ids()

    for message in messages:
        msg_id = message['id']
        if msg_id in processed_ids:
            continue

        msg = service.users().messages().get(userId='me', id=msg_id).execute()
        headers = {header['name']: header['value'] for header in msg['payload']['headers']}
        snippet = msg.get('snippet', '')

        email_data = {
            'id': msg_id,
            'from': headers.get('From', 'Unknown'),
            'subject': headers.get('Subject', 'No Subject'),
            'snippet': snippet
        }

        create_markdown_file(email_data)
        save_processed_id(msg_id)

def main():
    try:
        fetch_unread_emails()
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == '__main__':
    main()