"""Fetch secrets from Infisical and deploy via Dokploy.

Reusable CI script: reads Infisical secrets and pushes them as env vars
to a Dokploy compose service before triggering deployment.

Required env vars:
  INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, DOKPLOY_API_KEY

Optional env vars (override defaults):
  INFISICAL_URL, INFISICAL_HOST, INFISICAL_WORKSPACE_ID,
  INFISICAL_ENVIRONMENT, DOKPLOY_URL, COMPOSE_ID
"""

import json
import os
import urllib.request

INFISICAL_URL = os.environ.get("INFISICAL_URL", "http://172.17.0.1:80")
INFISICAL_HOST = os.environ.get("INFISICAL_HOST", "infisical.artesanosdigitalescom.com.mx")
WORKSPACE_ID = os.environ.get("INFISICAL_WORKSPACE_ID", "95e5961f-8e52-403c-b83b-479e5b422284")
INFISICAL_ENV = os.environ.get("INFISICAL_ENVIRONMENT", "dev")
COMPOSE_ID = os.environ.get("COMPOSE_ID", "ibcDGWxAp6qyvgMCm6UrM")
DOKPLOY_URL = os.environ.get("DOKPLOY_URL", "http://172.17.0.1:3000/api")


def infisical_login():
    client_id = os.environ["INFISICAL_CLIENT_ID"]
    client_secret = os.environ["INFISICAL_CLIENT_SECRET"]
    data = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode()
    req = urllib.request.Request(
        f"{INFISICAL_URL}/api/v1/auth/universal-auth/login", data=data, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Host", INFISICAL_HOST)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode())["accessToken"]


def fetch_secrets(token):
    url = f"{INFISICAL_URL}/api/v3/secrets/raw?workspaceId={WORKSPACE_ID}&environment={INFISICAL_ENV}&secretPath=/"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Host", INFISICAL_HOST)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode())["secrets"]


def push_env_to_dokploy(env_content):
    dokploy_key = os.environ["DOKPLOY_API_KEY"]
    payload = json.dumps({"composeId": COMPOSE_ID, "env": env_content}).encode()
    req = urllib.request.Request(f"{DOKPLOY_URL}/compose.update", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", dokploy_key)
    urllib.request.urlopen(req, timeout=10)


def trigger_deploy():
    dokploy_key = os.environ["DOKPLOY_API_KEY"]
    payload = json.dumps({"composeId": COMPOSE_ID}).encode()
    req = urllib.request.Request(f"{DOKPLOY_URL}/compose.deploy", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", dokploy_key)
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    print("=== Authenticating with Infisical ===")
    token = infisical_login()
    print("Token obtained")

    print("=== Fetching secrets from Infisical ===")
    secrets = fetch_secrets(token)
    env_lines = [f"{s['secretKey']}={s['secretValue']}" for s in secrets]
    env_content = "\n".join(env_lines)
    print(f"Fetched {len(env_lines)} secrets")

    print("=== Pushing secrets to Dokploy ===")
    push_env_to_dokploy(env_content)
    print("Secrets injected")

    print("=== Triggering deploy ===")
    trigger_deploy()
    print("Deploy triggered!")
