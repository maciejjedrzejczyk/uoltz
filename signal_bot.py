import time
import threading
import logging
import subprocess
import shlex
import re
import requests
import json
import os
import argparse

# Parse command line arguments
parser = argparse.ArgumentParser(description='Signal bot with LLM integration')
parser.add_argument('--model', type=str, default='local-model', help='LLM model name to use')
parser.add_argument('--nickname', type=str, default='@bot', help='Nickname to respond to (e.g., @bot, @assistant)')
parser.add_argument('--config', type=str, default='config.json', help='Configuration file path')
parser.add_argument('--log-level', type=str, default='DEBUG', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='Logging level')
parser.add_argument('--test-phone', type=str, default='<phone_number_used_for_testing>', help='Phone number to use for self-tests')
args = parser.parse_args()

# Default configuration
default_config = {
    "bot_phone_number": "<a_phone_number_used_to_register_a_bot_into_signal>", # Add a phone number used to register the bot in Signal
    "lmstudio_api_url": "http://<lmstudio_ip_address>:1234/v1/chat/completions", # Add LMSTudio IP address or hostname
    "docker_container": "signal-cli", # Add signal-cli docker container name
    "require_mention_in_direct_messages": True,
    "model": args.model, # Leave for a default model or indicate your own one
    "bot_nickname": args.nickname.lower(),  # Store in lowercase for case-insensitive matching
    "log_level": args.log_level, # Leave for a default model or indicate between 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    "test_phone_number": args.test_phone # Optional. Add a phone number used for testing the bot on Signal.
}

# Set up logging with parameterized level
logging.basicConfig(
    level=getattr(logging, args.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("signal_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("signal_bot")

# Configuration
CONFIG_FILE = args.config
GROUP_CACHE_FILE = "group_cache.json"  # File to store group information between runs



# Load configuration from file or create default
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info(f"Loaded configuration from {CONFIG_FILE}")
                
                # Override with command line arguments if provided
                if args.model != 'local-model':
                    config['model'] = args.model
                if args.nickname != '@bot':
                    config['bot_nickname'] = args.nickname.lower()
                if args.log_level != 'DEBUG':
                    config['log_level'] = args.log_level
                if args.test_phone != '<phone_number_used_for_testing>':
                    config['test_phone_number'] = args.test_phone
                
                return config
        else:
            # Create default config file
            with open(CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Created default configuration file at {CONFIG_FILE}")
            return default_config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return default_config

# Load configuration
config = load_config()

# Extract configuration variables
BOT_PHONE_NUMBER = config.get('bot_phone_number', '<a_phone_number_used_to_register_a_bot_into_signal>')
LMSTUDIO_API_URL = config.get('lmstudio_api_url', 'http://<lmstudio_ip_address>:1234/v1/chat/completions')
DOCKER_CONTAINER = config.get('docker_container', 'signal-cli')
REQUIRE_MENTION_IN_DIRECT_MESSAGES = config.get('require_mention_in_direct_messages', True)
MODEL_NAME = config.get('model', args.model)
BOT_NICKNAME = config.get('bot_nickname', args.nickname.lower())
TEST_PHONE_NUMBER = config.get('test_phone_number', args.test_phone)



logger.info(f"Bot configured with model: {MODEL_NAME} and nickname: {BOT_NICKNAME}")

# Function to load group cache from file
def load_group_cache():
    try:
        with open(GROUP_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Function to save group cache to file
def save_group_cache(groups):
    with open(GROUP_CACHE_FILE, 'w') as f:
        json.dump(groups, f, indent=2)

# Initialize group cache
group_cache = load_group_cache()

# Function to run docker exec commands with better output handling
def run_docker_command(command, check=True):
    full_command = f"docker exec {DOCKER_CONTAINER} {command}"
    logger.debug(f"Running command: {full_command}")
    
    try:
        # Use subprocess.Popen for more control over the process
        process = subprocess.Popen(
            shlex.split(full_command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Get stdout and stderr
        stdout, stderr = process.communicate()
        
        # Check return code
        if process.returncode != 0 and check:
            logger.error(f"Command failed with exit code {process.returncode}: {stderr}")
            return None
        
        # Log any stderr output even if command succeeded
        if stderr:
            logger.warning(f"Command produced stderr: {stderr}")
        
        return stdout.strip()
    except Exception as e:
        logger.error(f"Error running command: {str(e)}")
        return None

# Function to extract phone number from sender string
def extract_phone_number(sender_string):
    if not sender_string:
        return None
        
    # Extract the phone number using regex
    # Looking for patterns like <phone_number_used_for_testing>
    phone_match = re.search(r'\+\d+', sender_string)
    if phone_match:
        return phone_match.group(0)
    return None

# Function to send a message to a Signal group
def send_group_message(group_id, message):
    logger.info(f"Sending message to group {group_id}: {message[:50]}...")
    
    # Escape quotes in the message
    escaped_message = message.replace('"', '\\"')
    
    # Construct the command using the correct syntax
    command = f'signal-cli -u {BOT_PHONE_NUMBER} send -g {group_id} -m "{escaped_message}"'
    logger.debug(f"Group message command: {command}")
    
    result = run_docker_command(command)
    if result is not None:
        logger.info("Group message sent successfully")
        return True
    else:
        logger.error(f"Failed to send group message to {group_id}")
        return False

# Function to send a direct message to a user
def send_direct_message(recipient, message):
    # Extract identifier (phone number or UUID)
    identifier = extract_identifier(recipient)
    if not identifier:
        logger.error(f"Could not extract identifier from: {recipient}")
        return False
    
    logger.info(f"Sending direct message to {identifier}: {message[:50]}...")
    
    # Escape quotes in the message
    escaped_message = message.replace('"', '\\"')
    
    # Check if it's a UUID or phone number
    if re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', identifier, re.IGNORECASE):
        # For UUID-based users, use the -u flag
        command = f'signal-cli -u {BOT_PHONE_NUMBER} send -m "{escaped_message}" --uuid {identifier}'
    else:
        # For phone number-based users
        command = f'signal-cli -u {BOT_PHONE_NUMBER} send -m "{escaped_message}" {identifier}'
    
    result = run_docker_command(command)
    if result is not None:
        logger.info("Direct message sent successfully")
        return True
    else:
        logger.error("Failed to send direct message")
        return False
    
# Function to get a response from LMStudio
def get_lmstudio_response(prompt):
    # Don't process empty prompts
    if not prompt or prompt.strip() == "":
        return "I'm not sure what you're asking. Could you please provide more details?"
    
    logger.info(f"Sending prompt to LMStudio using model {MODEL_NAME}: {prompt[:50]}...")
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500
    }
    try:
        response = requests.post(LMSTUDIO_API_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            response_text = result['choices'][0]['message']['content']
            logger.info(f"Received response from LMStudio: {response_text[:50]}...")
            return response_text
        else:
            error_msg = f"Error: LMStudio returned status code {response.status_code}"
            logger.error(error_msg)
            return error_msg
    except Exception as e:
        error_msg = f"Error connecting to LMStudio: {str(e)}"
        logger.error(error_msg)
        return error_msg

# Function to check if a message is directed to the bot
def is_directed_to_bot(text):
    # Convert to lowercase for case-insensitive matching
    return BOT_NICKNAME in text.lower()

## Function to get group details directly from signal-cli with improved parsing
def get_group_details():
    global group_cache
    
    command = f'signal-cli -u {BOT_PHONE_NUMBER} listGroups -d'
    result = run_docker_command(command)
    
    groups = {}
    if result:
        logger.debug(f"Raw group list output: {result}")
        
        # Split the output into group blocks
        group_blocks = re.split(r'\n\s*\n', result)
        
        for block in group_blocks:
            if not block.strip():
                continue
                
            # Extract group name
            name_match = re.search(r'Name:\s+(.+?)(?:\n|$)', block)
            # Extract group ID - make sure to only get the ID part
            id_match = re.search(r'Id:\s+([^\s]+)', block)
            
            if name_match and id_match:
                group_name = name_match.group(1).strip()
                group_id = id_match.group(1).strip()
                groups[group_name] = group_id
                logger.info(f"Found group: {group_name} with ID: {group_id}")
        
        # Rest of the function remains the same
        
        if not groups:
            logger.warning("No groups found using primary pattern. Raw output: " + result)
            
            # Try alternative parsing if the regular parsing failed
            alt_matches = re.finditer(r'Id:\s+([^\s]+)\s+Name:\s+([^\n]+)', result)
            for match in alt_matches:
                group_id = match.group(1).strip()
                group_name = match.group(2).strip()
                groups[group_name] = group_id
                logger.info(f"Found group (alt method): {group_name} with ID: {group_id}")
    else:
        logger.error("Failed to get group list")
        
        # If we failed to get the current group list, use the cached version
        if group_cache:
            logger.info(f"Using cached group information ({len(group_cache)} groups)")
            groups = group_cache
    
    # Update our cache with any new information
    if groups:
        group_cache.update(groups)
        save_group_cache(group_cache)
    
    return groups

# Function to update group cache with a new group
def update_group_cache(group_name, group_id):
    global group_cache
    
    if group_name and group_id:
        group_cache[group_name] = group_id
        logger.info(f"Added/updated group in cache: {group_name} with ID: {group_id}")
        save_group_cache(group_cache)

# Function to list all known contacts
def list_contacts():
    logger.info("Listing all known contacts...")
    
    command = f'signal-cli -u {BOT_PHONE_NUMBER} listContacts'
    result = run_docker_command(command)
    
    if result:
        contacts = re.findall(r'Number: (\+\d+)', result)
        logger.info(f"Found {len(contacts)} contacts: {contacts}")
        return contacts
    else:
        logger.error("Failed to list contacts")
        return []
    


# Function to print detailed group member information
def print_group_members():
    logger.info("Printing detailed group member information...")
    
    command = f'signal-cli -u {BOT_PHONE_NUMBER} listGroups -d'
    result = run_docker_command(command)
    
    if result:
        # Find all groups
        group_blocks = re.split(r'\n\s*\n', result)
        
        for block in group_blocks:
            if not block.strip():
                continue
            
            # Extract group name
            name_match = re.search(r'Name:\s+(.+?)(?:\n|$)', block)
            if name_match:
                group_name = name_match.group(1).strip()
                logger.info(f"Group: {group_name}")
                
                # Extract members
                members_match = re.search(r'Members:\s+\[(.*?)\]', block)
                if members_match:
                    members_str = members_match.group(1)
                    # Extract all identifiers (both phone numbers and UUIDs)
                    phone_numbers = re.findall(r'\+\d+', members_str)
                    uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', members_str, re.IGNORECASE)
                    
                    logger.info(f"  Phone number members: {phone_numbers}")
                    logger.info(f"  UUID members: {uuids}")
    else:
        logger.warning("Could not get group information")

# Function to parse the text output of signal-cli receive command
# In parse_received_messages function:
def parse_received_messages(output):
    if not output:
        return []
    
    messages = []
    
    # Log the raw output for debugging
    if args.log_level == 'DEBUG':
        logger.debug(f"Raw receive output: {output}")
    
    # Split the output into message blocks
    message_blocks = re.split(r'\nEnvelope from:', output)
    
    if not message_blocks[0].startswith('Envelope from:'):
        message_blocks[0] = 'Envelope from:' + message_blocks[0]
    
    logger.info(f"Processing {len(message_blocks)} message blocks")
    
    for block in message_blocks:
        if not block.strip():
            continue
            
        # Create a message dictionary
        message = {}
        
        # Extract timestamp
        timestamp_match = re.search(r'Timestamp: (\d+)', block)
        if timestamp_match:
            message['timestamp'] = int(timestamp_match.group(1))
        
        # Extract sender - look for both phone numbers and UUIDs
        sender_match = re.search(r'Envelope from: (.+?)(?:\n|$)', block)
        if sender_match:
            sender_string = sender_match.group(1).strip()
            message['sourceNumber'] = sender_string
            
            # Try to extract a cleaner identifier
            identifier = extract_identifier(sender_string)
            if identifier:
                message['sourceIdentifier'] = identifier
                logger.info(f"Found message from identifier: {identifier}")
        
        # Check if this is a receipt message (delivery or read receipt)
        if re.search(r'Received a receipt message', block):
            message['isReceipt'] = True
            # We don't need to process these further
            messages.append(message)
            continue
        
        # Extract message content
        content_match = re.search(r'Body: (.+?)(?:\n|$)', block)
        if content_match:
            message['message'] = content_match.group(1).strip()
        
        # Check if it's a group message - look for Group info section
        group_info_section = re.search(r'Group info:(.*?)(?=\n\n|\Z)', block, re.DOTALL)
        if group_info_section:
            group_info = group_info_section.group(1).strip()
            logger.debug(f"Found group info section: {group_info}")
            
            # Extract group name
            group_name_match = re.search(r'Name:\s+(.+?)(?:\n|$)', group_info)
            if group_name_match:
                group_name = group_name_match.group(1).strip()
                message['groupName'] = group_name
            
            # Extract group ID - try multiple patterns
            group_id_match = re.search(r'ID:\s+(.+?)(?:\n|$)', group_info)
            if not group_id_match:
                group_id_match = re.search(r'Id:\s+([^\s]+)', group_info)
            
            if group_id_match:
                direct_group_id = group_id_match.group(1).strip()
                message['groupId'] = direct_group_id
                logger.debug(f"Found group ID in message: {direct_group_id}")
                
                # Update our group cache with this information
                if 'groupName' in message:
                    update_group_cache(message['groupName'], direct_group_id)
            
            # Extract sender UUID for group messages
            sender_uuid_match = re.search(r'Sender: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', group_info, re.IGNORECASE)
            if sender_uuid_match:
                message['senderUuid'] = sender_uuid_match.group(1)
                logger.debug(f"Found sender UUID in group message: {message['senderUuid']}")
        
        if message:
            messages.append(message)
    
    logger.debug(f"Parsed {len(messages)} messages")
    return messages

# Function to receive and process messages
def receive_messages():
    global LAST_PROCESSED_TIME
    
    logger.info(f"Starting to receive messages from timestamp: {int(time.time() * 1000)}")
    LAST_PROCESSED_TIME = int(time.time() * 1000)
    
    # Get group details for reference
    groups = get_group_details()
    logger.info(f"Found {len(groups)} groups: {list(groups.keys())}")
    
    while True:
        try:
            # Receive new messages with --ignore-attachments to improve performance
            command = f'signal-cli -u {BOT_PHONE_NUMBER} receive --ignore-attachments'
            output = run_docker_command(command)
            
            # Log raw output at DEBUG level to see all incoming messages
            if args.log_level == 'DEBUG':
                logger.debug(f"Raw receive output: {output}")
            
            if output:
                messages = parse_received_messages(output)
                
                # Rest of the function remains the same
                
                for message in messages:
                    # Log the message for debugging
                    logger.debug(f"Processing message: {message}")
                    
                    # Extract necessary information
                    timestamp = message.get('timestamp', 0)
                    
                    # Skip if we've already processed this message
                    if timestamp <= LAST_PROCESSED_TIME:
                        logger.debug(f"Skipping already processed message: {timestamp}")
                        continue
                    
                    # Update the last processed timestamp
                    LAST_PROCESSED_TIME = max(LAST_PROCESSED_TIME, timestamp)
                    
                    # Skip receipt messages
                    if message.get('isReceipt', False):
                        logger.debug(f"Skipping receipt message with timestamp: {timestamp}")
                        continue
                    
                    # Skip messages without actual content
                    if 'message' not in message or not message['message']:
                        logger.debug(f"Skipping message without content: {message}")
                        continue
                    
                    # Skip messages without actual content
                    if 'message' not in message or not message['message']:
                        logger.debug(f"Skipping message without content: {message}")
                        continue
                    
                    sender = message.get('sourceNumber', 'Unknown')
                    text = message.get('message', '')
                    
                    # Skip messages from the bot itself
                    if extract_phone_number(sender) == BOT_PHONE_NUMBER:
                        logger.debug(f"Skipping message from self: {text}")
                        continue
                    
                    # Check if the message is directed to the bot
                    message_for_bot = is_directed_to_bot(text)
                    
                    # Check if it's a group message by looking for groupName
                    if 'groupName' in message:
                        group_name = message.get('groupName', 'Unknown Group')
                        logger.info(f"Group message in {group_name} from {sender}: {text}")
                        
                        # Only respond if the message is directed to the bot
                        if message_for_bot:
                            logger.info(f"Bot mentioned in group message: {text}")
                            
                            # Remove the bot nickname and process the query
                            query = re.sub(re.escape(BOT_NICKNAME), '', text, flags=re.IGNORECASE).strip()
                            if not query:
                                query = "Hello! How can I help you?"
                            
                            # Get response from LMStudio
                            response = get_lmstudio_response(query)
                            
                            # We need to find the group ID for this group
                            group_id = None
                            
                            # First check if we have a groupId in the message
                            if 'groupId' in message and message['groupId']:
                                group_id = message['groupId']
                                logger.debug(f"Using group ID from message: {group_id}")
                            
                            # If not, try to find it in our groups dictionary or cache
                            elif group_name in groups:
                                group_id = groups[group_name]
                                logger.debug(f"Using group ID from groups dictionary: {group_id}")
                            elif group_name in group_cache:
                                group_id = group_cache[group_name]
                                logger.debug(f"Using group ID from cache: {group_id}")
                            
                            # If we have a group ID, send the response to the group
                            if group_id:
                                logger.info(f"Sending response to group {group_name} (ID: {group_id})")
                                success = send_group_message(group_id, response)
                                logger.info(f"Group message response sent: {success}")
                                
                                # If sending failed, try refreshing our group list and try again
                                if not success:
                                    logger.warning(f"Failed to send to group {group_name}, refreshing group list and trying again")
                                    refreshed_groups = get_group_details()
                                    if group_name in refreshed_groups:
                                        new_group_id = refreshed_groups[group_name]
                                        if new_group_id != group_id:
                                            logger.info(f"Group ID changed for {group_name}: {group_id} -> {new_group_id}")
                                            group_id = new_group_id
                                            success = send_group_message(group_id, response)
                                            logger.info(f"Second attempt group message response sent: {success}")
                                
                                # If still failed, fall back to direct message
                                if not success:
                                    logger.error(f"All attempts to send to group failed, falling back to direct message")
                                    send_direct_message(sender, f"(Response to group message in {group_name}): {response}")
                            else:
                                logger.error(f"Could not find group ID for group {group_name}")
                                # Fallback to direct message if we can't find the group ID
                                logger.info(f"Sending fallback direct message to {sender}")
                                send_direct_message(sender, f"(Response to group message in {group_name}): {response}")
                        else:
                            logger.debug(f"Ignoring group message not directed to bot: {text}")
                    
                    # Direct message
                    else:
                        logger.info(f"Direct message from {sender}: {text}")
                        
                        # Check if we require mentions in direct messages
                        if REQUIRE_MENTION_IN_DIRECT_MESSAGES:
                            if message_for_bot:
                                logger.info(f"Bot mentioned in direct message: {text}")
                                
                                # Remove the bot nickname and process the query
                                query = re.sub(re.escape(BOT_NICKNAME), '', text, flags=re.IGNORECASE).strip()
                                if not query:
                                    query = "Hello! How can I help you?"
                                
                                # Get response from LMStudio
                                response = get_lmstudio_response(query)
                                
                                # Send the response back to the sender
                                send_direct_message(sender, response)
                            else:
                                logger.debug(f"Ignoring direct message not directed to bot: {text}")
                        else:
                            # Process all direct messages regardless of mention
                            response = get_lmstudio_response(text)
                            send_direct_message(sender, response)
            
            # Sleep to avoid hammering the CLI
            time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in message receiving loop: {str(e)}", exc_info=True)
            time.sleep(5)  # Wait a bit longer if there's an error

# Function to trust all group members
def trust_all_group_members():
    logger.info("Ensuring all group members are trusted...")
    
    # Get all groups
    command = f'signal-cli -u {BOT_PHONE_NUMBER} listGroups -d'
    result = run_docker_command(command)
    
    if result:
        # Find all members in the output
        groups_match = re.finditer(r'Members:\s+\[(.*?)\]', result)
        all_members = set()
        
        for match in groups_match:
            members_str = match.group(1)
            # Extract all identifiers (both phone numbers and UUIDs)
            phone_numbers = re.findall(r'\+\d+', members_str)
            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', members_str, re.IGNORECASE)
            
            all_members.update(phone_numbers)
            all_members.update(uuids)
        
        # Remove our own number
        if BOT_PHONE_NUMBER in all_members:
            all_members.remove(BOT_PHONE_NUMBER)
        
        logger.info(f"Found {len(all_members)} unique members across all groups: {all_members}")
        
        # Trust each member
        for member in all_members:
            if re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', member, re.IGNORECASE):
                # For UUID-based users
                command = f'signal-cli -u {BOT_PHONE_NUMBER} trust --uuid {member}'
            else:
                # For phone number-based users
                command = f'signal-cli -u {BOT_PHONE_NUMBER} trust -a {member}'
            
            result = run_docker_command(command)
            logger.info(f"Trusted member {member}: {result is not None}")
    else:
        logger.warning("Could not get group information to trust members")
    
    logger.info("Finished trusting all group members")

# Function to test the bot by sending a message to yourself
def test_bot():
    logger.info("Running bot self-test...")
    send_direct_message(TEST_PHONE_NUMBER, f"Bot is now online and ready to respond to messages! Please use {BOT_NICKNAME} to interact with me. I'm using the {MODEL_NAME} model.")

# Function to request sync messages
def request_sync_messages():
    logger.info("Requesting sync messages...")
    
    command = f'signal-cli -u {BOT_PHONE_NUMBER} sendSyncRequest'
    result = run_docker_command(command)
    
    if result is not None:
        logger.info("Successfully requested sync messages")
        return True
    else:
        logger.error("Failed to request sync messages")
        return False
    
# Heartbeat function to ensure bot is running and refresh group cache periodically
def heartbeat():
    while True:
        logger.info(f"Bot heartbeat - still running (using model: {MODEL_NAME}, nickname: {BOT_NICKNAME})")
        
        # Refresh group cache every hour
        refresh_group_cache()
        
        # Request sync messages every hour
        request_sync_messages()
        
        time.sleep(3600)  # Sleep for 1 hour

# Function to test group messaging for all known groups
def test_all_groups():
    # Get list of groups
    groups = get_group_details()
    if groups:
        logger.info(f"Testing messages to {len(groups)} groups")
        for group_name, group_id in groups.items():
            logger.info(f"Sending test message to group {group_name} (ID: {group_id})")
            success = send_group_message(group_id, f"Bot is now online and ready to respond to group messages! Please use {BOT_NICKNAME} to interact with me. I'm using the {MODEL_NAME} model.")
            logger.info(f"Test message to group {group_name} sent: {success}")
    else:
        logger.error("Could not find any groups")

# Function to manually send a message to a specific group
def send_to_group(group_name, message):
    # First check our cache
    if group_name in group_cache:
        group_id = group_cache[group_name]
        logger.info(f"Manually sending message to group {group_name} (ID: {group_id}) from cache")
        success = send_group_message(group_id, message)
        if success:
            logger.info(f"Manual message to group {group_name} sent successfully")
            return True
    
    # If not in cache or sending failed, refresh group list
    groups = get_group_details()
    if group_name in groups:
        group_id = groups[group_name]
        logger.info(f"Manually sending message to group {group_name} (ID: {group_id}) from fresh list")
        success = send_group_message(group_id, message)
        logger.info(f"Manual message to group {group_name} sent: {success}")
        return success
    else:
        logger.error(f"Group {group_name} not found")
        return False

# Function to manually send a message to a group using a specific ID
def send_to_group_id(group_id, message):
    logger.info(f"Manually sending message to group ID: {group_id}")
    success = send_group_message(group_id, message)
    logger.info(f"Manual message to group ID {group_id} sent: {success}")
    return success

# Function to list groups for debugging
def list_groups():
    groups = get_group_details()
    if groups:
        for name, group_id in groups.items():
            logger.info(f"Group: {name}, ID: {group_id}")
        return True
    else:
        logger.error("Failed to list groups or no groups found")
        return False

# Function to refresh the group cache
def refresh_group_cache():
    global group_cache
    
    logger.info("Refreshing group cache")
    groups = get_group_details()
    if groups:
        # Update our cache with the fresh information
        group_cache.update(groups)
        save_group_cache(group_cache)
        logger.info(f"Group cache refreshed with {len(groups)} groups")
        return True
    else:
        logger.error("Failed to refresh group cache")
        return False
    
# Function to extract identifier (phone number or UUID) from sender string
def extract_identifier(sender_string):
    if not sender_string:
        return None
    
    # Try to extract phone number first (patterns like <phone_number_used_for_testing>)
    phone_match = re.search(r'\+\d+', sender_string)
    if phone_match:
        return phone_match.group(0)
    
    # If no phone number, try to extract UUID (patterns like 49429e81-afa4-41ae-878a-8659e5cabc75)
    uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', sender_string, re.IGNORECASE)
    if uuid_match:
        return uuid_match.group(0)
    
    # If neither, return the whole string as a fallback
    return sender_string
# # Function to verify group subscriptions
# def verify_group_subscriptions():
#     logger.info("Verifying group subscriptions...")
    
#     groups = get_group_details()
    
#     for group_name, group_id in groups.items():
#         # Update group - just use the group ID without any additional arguments
#         command = f'signal-cli -u {BOT_PHONE_NUMBER} updateGroup -g {group_id}'
#         result = run_docker_command(command)
#         logger.info(f"Updated group {group_name}: {result is not None}")
    
#     logger.info("Finished verifying group subscriptions")
# Heartbeat function to ensure bot is running and refresh group cache periodically
def heartbeat():
    while True:
        logger.info(f"Bot heartbeat - still running (using model: {MODEL_NAME}, nickname: {BOT_NICKNAME})")
        
        # Refresh group cache every hour
        refresh_group_cache()
        
        time.sleep(3600)  # Sleep for 1 hour

# Start the message receiving loop in a separate thread
if __name__ == "__main__":
    logger.info(f"Starting Signal bot with model: {MODEL_NAME} and nickname: {BOT_NICKNAME}...")
    
    # List groups for debugging
    list_groups()
        # List all contacts
    list_contacts()
    
    # Trust all group members
    trust_all_group_members()

    # Verify group subscriptions
    # verify_group_subscriptions()
    print_group_members()
    # Request sync messages
    request_sync_messages()
    
    # Rest of the function remains the same
    
    # Uncomment to run a self-test (replace the number with yours)
    # test_bot()
    
    # Uncomment to test messaging to all groups
    # test_all_groups()
    
    # Start the message receiving thread
    receive_thread = threading.Thread(target=receive_messages)
    receive_thread.daemon = True
    receive_thread.start()
    
    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=heartbeat)
    heartbeat_thread.daemon = True
    heartbeat_thread.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")