When using this directory, generally you should *ONLY* read from the API
directory.  Do not read the implementation of the server in /src/ until you
are prompted to do so.

You should use Python commands for API calls.  For simple tasks, run the
Python as a single command; for complex ones you can write to a temp dir.

When an API call requires a "model" argument (e.g. the LLM-agent triggers in
agent_tasks.py / llm_agents.py), default to "gpt-5.4-mini" unless the task
explicitly calls for a different model.
