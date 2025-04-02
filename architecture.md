# Signal Bot Architecture and Components

## System Overview

The Signal Bot integrates several components to enable AI-powered conversations through Signal messenger. This document outlines the key components, their interactions, and the data flow through the system.

## Core Components

### 1. Signal Bot (Python Application)

**Purpose**: The central controller that manages message processing, AI interactions, and response routing.

**Key Features**:
- Message reception and parsing
- Command handling
- Group chat management
- Configuration management
- Logging and error handling

**Technologies**:
- Python 3.7+
- Subprocess module for Docker interactions
- Regular expressions for message parsing
- Threading for concurrent operations

### 2. signal-cli (Docker Container)

**Purpose**: Provides a command-line interface to the Signal messenger service.

**Key Features**:
- Signal account registration and verification
- Message sending and receiving
- Group management
- Contact management

**Technologies**:
- Java-based CLI application
- Docker containerization for isolation and portability

### 3. LMStudio (Local Application)

**Purpose**: Hosts and runs large language models locally.

**Key Features**:
- Local LLM model hosting
- REST API for model interactions
- Model switching and configuration
- Text generation with various parameters

**Technologies**:
- REST API
- Local model inference
- JSON for data exchange

### 4. Persistent Storage

**Purpose**: Maintains configuration and state between bot restarts.

**Key Components**:
- `config.json`: Stores bot configuration
- `group_cache.json`: Caches group information
- `signal_bot.log`: Records detailed operation logs

## Data Flow and Interactions

### 1. Initialization Flow

1. **Bot Startup**:
   - Load configuration from `config.json` or create default
   - Set up logging based on configured level
   - Initialize group cache from `group_cache.json`

2. **Signal Connection**:
   - List available groups via signal-cli
   - Trust all group members
   - Cache group information

3. **System Readiness**:
   - Start message receiving thread
   - Start heartbeat thread for periodic maintenance
   - Log system ready status

### 2. Message Processing Flow

1. **Message Reception**:
   - Execute `signal-cli receive` command
   - Parse raw output into structured message objects
   - Filter out receipts and already processed messages

2. **Message Classification**:
   - Identify direct vs. group messages
   - Extract sender information (phone number or UUID)
   - Determine if message mentions the bot

3. **Query Processing**:
   - For messages mentioning the bot, extract the query
   - Remove bot nickname from the query text
   - Prepare query for LLM processing

### 3. AI Interaction Flow

1. **LLM Query**:
   - Construct JSON payload with query and parameters
   - Send HTTP POST request to LMStudio API
   - Receive and parse JSON response

2. **Response Handling**:
   - Extract generated text from LLM response
   - Format response if needed
   - Prepare for delivery back to Signal

### 4. Response Delivery Flow

1. **Group Message Responses**:
   - Identify correct group ID from message or cache
   - Construct signal-cli command for group message
   - Execute command and verify delivery

2. **Direct Message Responses**:
   - Extract recipient identifier (phone or UUID)
   - Construct appropriate signal-cli command
   - Execute command and verify delivery

3. **Error Handling**:
   - If primary delivery fails, attempt alternative methods
   - Fall back to direct message if group delivery fails
   - Log delivery status and any errors

### 5. Maintenance Flow

1. **Periodic Tasks** (via heartbeat thread):
   - Refresh group cache hourly
   - Request sync messages to ensure all messages are received
   - Log bot status and health

2. **Cache Updates**:
   - When new group information is discovered, update cache
   - Persist updated cache to `group_cache.json`
   - Use cached information when live data is unavailable

## Command and Control

### 1. Command-Line Interface

The bot accepts various command-line arguments:
- `--model`: Specifies which LLM model to use
- `--nickname`: Sets the bot's mention name
- `--config`: Points to configuration file location
- `--log-level`: Controls logging verbosity
- `--test-phone`: Defines phone number for self-tests

### 2. Configuration File

The `config.json` file stores persistent settings:
- Bot phone number
- LMStudio API URL
- Docker container name
- Model name
- Bot nickname
- Log level
- Test phone number
- Direct message behavior settings

### 3. Logging System

The logging system provides visibility into bot operations:
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- File and console output
- Timestamp and component information
- Detailed error reporting

## Security Considerations

1. **Message Privacy**:
   - All message processing happens locally
   - No message content is sent to external services
   - LLM inference occurs on the local machine

2. **Authentication**:
   - Bot uses a dedicated Signal account
   - signal-cli handles all Signal protocol security
   - No additional authentication is required

3. **Data Storage**:
   - Configuration may contain sensitive information (phone numbers)
   - Group cache stores group IDs and names
   - Logs may contain message snippets and phone numbers

## Integration Points

1. **Signal Integration**:
   - Via signal-cli Docker container
   - Commands executed through subprocess
   - Text-based parsing of command output

2. **LMStudio Integration**:
   - REST API calls to local endpoint
   - JSON-formatted requests and responses
   - HTTP-based communication

3. **System Integration**:
   - File system for configuration and logging
   - Docker for signal-cli container management
   - Process management for long-running operation

This architecture provides a flexible, maintainable system that connects Signal messaging with local AI capabilities, all while maintaining user privacy and data security.