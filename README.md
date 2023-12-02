# Threadflow

...


## Getting started

...

```
pip install uvicorn fastapi pydantic pyyaml openai rapidfuzz python-multipart python-jose[cryptography] passlib[bcrypt]
```

```
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

...

```
# On UNIX
OPENAI_API_TYPE=azure
OPENAI_API_VERSION=2023-05-15
OPENAI_API_BASE=https://switzerlandnorth.api.cognitive.microsoft.com/
OPENAI_API_KEY=<key>

# On Windows
set OPENAI_API_TYPE=azure
set OPENAI_API_VERSION=2023-05-15
set OPENAI_API_BASE=https://switzerlandnorth.api.cognitive.microsoft.com/
set OPENAI_API_KEY=<key>
```

...

```
uvicorn threadflow.main:app --port 8000 --reload
```


## Relevant links

 * https://restfulapi.net/resource-naming/
 * https://github.com/openai/openai-python
