# Zoo Tour Guide Agent

This project implements a conversational AI agent that acts as a virtual tour guide for a zoo. It's designed to answer user questions about animals by combining information from a general knowledge base (Wikipedia) with (planned) internal zoo data.

The agent is built using the [Google Agent Development Kit (ADK)](https://developers.google.com/agent-builder/docs) and leverages a multi-agent architecture to handle user requests in a structured way.

## Features

- **Conversational Interface**: Greets users and naturally captures their questions.
- **Multi-Agent Workflow**: Utilizes a sequence of specialized agents for research and response generation.
- **External Knowledge Integration**: Uses Wikipedia to fetch general facts about animals.
- **Extensible Design**: Structured to easily incorporate new tools, such as an internal zoo database for animal-specific details (e.g., names, locations within the zoo).

## How It Works (Architecture)

The application is orchestrated by a root agent (`greeter`) that delegates tasks to a sequential workflow (`tour_guide_workflow`). This workflow ensures a clean separation of concerns between gathering information and presenting it to the user.

The agent flow is as follows:

1.  **`greeter` (Root Agent)**:
    -   This is the main entry point.
    -   It greets the user and waits for their question about an animal.
    -   It uses the `add_prompt_to_state` tool to save the user's query.
    -   It then transfers control to the `tour_guide_workflow`.

2.  **`tour_guide_workflow` (Sequential Agent)**:
    This agent manages a two-step process to answer the user's query.

    -   **Step 1: `comprehensive_researcher`**:
        -   Its goal is to gather all necessary information to answer the user's prompt.
        -   It has access to a **Wikipedia tool** for general knowledge (e.g., "What do red pandas eat?").
        -   The agent is designed to be extended with a tool for accessing internal zoo data (e.g., "What is our red panda's name and where can I find her?").
        -   It synthesizes its findings into a `research_data` output.

    -   **Step 2: `response_formatter`**:
        -   This agent takes the `research_data` collected by the researcher.
        -   It formats this data into a friendly, engaging, and easy-to-read response, acting as the "voice" of the zoo tour guide.

## Project Structure

```
customer_guide_agent/
├── agent.py          # Main application file defining the agents and workflow.
├── requirements.txt  # Python dependencies.
└── .env              # Environment variables (you need to create this).
```

## Setup and Installation

1.  **Clone the Repository**

2.  **Create a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables**
    Create a file named `.env` in the root of the project directory and add the following line. This specifies the generative model the agents will use.

    ```
    MODEL="gemini-1.5-pro-latest"
    ```

5.  **Google Cloud Authentication**
    The application uses Google Cloud Logging. Ensure your local environment is authenticated with Google Cloud:
    ```bash
    gcloud auth application-default login
    ```

## Running the Agent

This project defines the agent's logic. To run it, you will need an entry point that loads the `root_agent` and starts an interaction loop. You can use the Google ADK's built-in `adk.start_repl_loop()` for a command-line interface.