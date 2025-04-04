# Uoltz - a Signal Bot with local LLM Integration

This bot allows you to interact with AI language models directly from your Signal chats, both in direct messages and group conversations.

![Uoltz Bot|883×1920,10%](./uoltz-animation.gif)

## Features

- **AI-Powered Responses**: Connect to any LLM model running in LMStudio
- **Group Chat Support**: Interact with the bot in both direct messages and group chats
- **Customizable Nickname**: Configure how users mention the bot (e.g., @bot, @assistant, @uoltz)
- **Dynamic Group Handling**: Works with any group you add the bot to, no hardcoding required
- **Persistent Configuration**: Settings and group information are saved between restarts
- **Comprehensive Logging**: Detailed logs to help with debugging and monitoring
- **UUID Support**: Works with both phone number and UUID-based Signal users
- **Configurable via CLI**: Easy command-line options for customization

## How does Uoltz work

![Uoltz Bot](./uoltz-diagram.png)

Here's a detailed description of each step in the flow:

### Step 1: User Message
A user sends a message in Signal that mentions the bot (e.g., "@waltz tell me a joke"). This message is sent through the Signal messaging platform, initiating the interaction flow.

### Step 2: Capture Message
The Signal Bot (signal_bot.py) continuously listens for incoming messages through the Signal CLI interface. When a message arrives, the bot captures it and processes the content to determine if it contains a mention of the bot's nickname (@waltz).

### Step 3: Submit Prompt to LMStudio
Once the bot detects it has been mentioned, it extracts the actual query by removing the mention prefix ("tell me a joke"). The bot then formats this query and submits it as a prompt to LMStudio's API, which hosts the local language model.

### Step 4: Prompt Response
LMStudio processes the prompt using the configured language model (e.g., Llama 3.2) and generates an appropriate response. This response is then sent back to the Signal Bot as a completion.

### Step 5: Forward Prompt Response
The Signal Bot receives the AI-generated response from LMStudio and formats it appropriately. It then uses the Signal CLI to send this response back to the original conversation, whether it's a direct message or a group chat.

### Step 6: User Receives Response
The user receives the AI-generated response through Signal. In the example shown, the bot responds to the joke request with the punchline "Because it was two-tired."

For more information about the architecture and components, please refer to [this document](./architecture.md).

## Prerequisites

- Python 3.7+ installed on your system
- A registered Signal account for the bot (with a dedicated phone number). For more information, please refer to [signal-cli documentation](https://github.com/AsamK/signal-cli/wiki/Registration-with-captcha).
- [signal-cli](https://github.com/AsamK/signal-cli) installed and running in a Docker container
- [LMStudio](https://lmstudio.ai/) running with at least one local model

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/maciejjedrzejczyk/uoltz.git
   cd uoltz
   ```

2. Install the required Python packages:
   ```bash
   pip install requests
   ```

## Configuration

The bot can be configured through command-line arguments or a configuration file:

```bash
python signal_bot.py --model "llama-3.2-3b-instruct" --nickname "@uoltz" --log-level INFO --test-phone "+1234567890"
```

Available command-line options:
- `--model`: The LLM model name to use in LMStudio (default: "local-model")
- `--nickname`: The name users should use to mention the bot (default: "@bot")
- `--config`: Path to the configuration file (default: "config.json")
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--test-phone`: Phone number to use for self-tests

The first time you run the bot, it will create a default configuration file (`config.json`) that you can edit:

```json
{
  "bot_phone_number": "+1234567890",
  "lmstudio_api_url": "http://localhost:1234/v1/chat/completions",
  "docker_container": "signal-cli",
  "require_mention_in_direct_messages": true,
  "model": "local-model",
  "bot_nickname": "@bot",
  "log_level": "INFO",
  "test_phone_number": "+1234567890"
}
```

## Running the Bot

Start the bot with:

```bash
python signal_bot.py
```

The bot will:
1. Connect to the signal-cli Docker container
2. List all groups it's a member of
3. Start listening for messages
4. Respond to messages that mention its nickname

To stop the bot, press Ctrl+C.

## Using the Bot

### Direct Messages

1. Start a direct conversation with the bot's phone number in Signal
2. Send a message that includes the bot's nickname your configured earlier (e.g., "@bot tell me a joke")
3. The bot will respond with an AI-generated answer

### Group Chats

1. Add the bot to a Signal group
2. Mention the bot in your message (e.g., "@bot tell me a joke about Donald Duck?")
3. The bot will respond in the group chat with an AI-generated answer

## Customizing the LLM

The bot connects to LMStudio's API, allowing you to use any model you have loaded:

1. Open LMStudio and load your preferred model
2. Ensure the API server is running (click "Start Server" in LMStudio)
3. Update the bot's configuration to use your model name:
   ```bash
   python signal_bot.py --model "llama-3.2-3b-instruct"
   ```

## Troubleshooting

### Bot Not Responding

- Check that signal-cli is running: `docker ps | grep signal-cli`
- Verify the bot's phone number is correctly registered
- Ensure LMStudio is running with the API server enabled
- Check the logs for errors: `tail -f signal_bot.log`

### Group Messages Not Working

- Make sure the bot is properly added to the group
- Verify you're mentioning the bot with the correct nickname
- Check if the group has any restrictions on who can send messages

### Connection Issues with LMStudio

- Verify LMStudio is running and the API server is started
- Check the API URL in the configuration file
- Ensure the model name matches exactly what's in LMStudio

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Acknowledgments

- [signal-cli](https://github.com/AsamK/signal-cli) for providing the command-line interface to Signal
- [LMStudio](https://lmstudio.ai/) for the local LLM hosting
- All contributors and users of this bot