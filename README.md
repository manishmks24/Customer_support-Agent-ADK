# Customer Intent Router Agent

This project implements an intelligent triage microservice for customer support. It's designed to receive a customer query, enrich it with data from an internal database, and route it to the appropriate support team with a specific priority.

The agent is built using the [Google Agent Development Kit (ADK)](https://developers.google.com/agent-builder/docs) and leverages a multi-agent architecture to handle user requests in a structured way.

## Features

- **Sequential Processing Pipeline**: Uses a multi-agent workflow to ensure each step of the triage process is handled by a specialized agent.
- **Structured Data Extraction**: Parses free-form customer queries into structured data (like `order_id` or `user_id`).
- **Database Integration**: Simulates looking up customer and order details (like warranty status) from a SQL database.
- **Rule-Based Routing**: Applies a clear set of business rules to the combined data to make a routing decision.
- **Strict Output Schema**: Produces a JSON object validated by Pydantic, ensuring reliable integration with downstream systems like CRMs or ticketing platforms.

## How It Works (Architecture)

The application is orchestrated by a root agent (`greeter`) that delegates tasks to a sequential workflow (`intent_router_workflow`). This workflow ensures a clean separation of concerns between understanding the query, gathering data, and making a decision.

The agent flow is as follows:

1.  **`greeter` (Root Agent)**:
    -   This is the main entry point.
    -   It greets the customer and uses the `save_customer_query` tool to save the user's raw message into the agent's state.
    -   It then transfers control to the `intent_router_workflow`.

2.  **`intent_router_workflow` (Sequential Agent)**:
    This agent manages a three-step process to triage the support ticket.

    -   **Step 1: `intent_extractor`**:
        -   Reads the raw customer query from state.
        -   Extracts key information like `order_id`, `user_id`, and a summary of the issue.
        -   Saves this structured data to the agent's state as `EXTRACTED_INTENT`.

    -   **Step 2: `db_lookup`**:
        -   Uses the identifiers from `EXTRACTED_INTENT` to call the `query_order_database` tool.
        -   This tool simulates a lookup against a SQL database to find order details and warranty status.
        -   The result is saved to the agent's state as `DB_RESULT`.

    -   **Step 3: `intent_router`**:
        -   This agent synthesizes all the information available in the state: `CUSTOMER_QUERY`, `EXTRACTED_INTENT`, and `DB_RESULT`.
        -   It applies a predefined set of routing rules to this context.
        -   It produces the final `ROUTING_DECISION` as a JSON object containing the `route`, `priority`, `reason`, and a `confidence` score.

## Project Structure

```
customer_guide_agent/
├── agent.py          # Main application file defining the agents and workflow.
├── requirements.txt  # Python dependencies.
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

4.  **Google Cloud Authentication**
    The application uses Google Cloud Logging. Ensure your local environment is authenticated with Google Cloud:
    ```bash
    gcloud auth application-default login
    ```

## Running the Agent

This project is designed to be run as a web service using the Google Agent Development Kit (ADK), as recommended in the `agent.py` docstring.

If you have made changes to the `agent.py` file, deploying them is as simple as stopping the current web server (if it's running) and starting it again with the updated code.

1.  **Stop the Old Server**: If the `adk web` command is currently running in a terminal, stop it by pressing `Ctrl+C`.

2.  **Start the New Server**: From your terminal in the project's root directory, run the following command:
    ```bash
    adk web --port 8080 --allow_origins="*"
    ```

This will start a local web server with your latest code changes. You can then interact with the agent by sending POST requests to the server or by using the Web Preview feature if you are running in a supported environment like Google Cloud Shell.