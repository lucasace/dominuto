# Dominuto

A simple URL shortener built as part of Tally Code Brewers Hackathon
https://dominuto.herokuapp.com/

## Local Development
1. ```bash
    pip3 install requirements.txt
    ```
2. ```bash
    $MONGODB_URL=<Enter your db url here>
    $KEY=<Enter your Fernet key here>
    ```
3. ```bash
    uvicorn app.main:app --port=5000 --reload
  ```
4. Visit http://localhost:5000
