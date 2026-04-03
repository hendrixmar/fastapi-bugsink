"""Deploy fastapi-bugsink to el-telar-ssh via Dokploy API.

NOTE: Dokploy's Docker provider tries to pull from a registry, so for local
images, build on the server and run with docker directly:

    ssh el-telar-ssh
    cd /tmp/fastapi-bugsink
    docker build -t fastapi-bugsink:latest .
    docker run -d --name fastapi-bugsink \\
        --network dokploy-network \\
        --add-host bugsink.artesanosdigitalescom.com.mx:10.0.1.31 \\
        -e 'SENTRY_DSN=http://ffc27113-eaca-40aa-b322-eef262b2e2f0@bugsink.artesanosdigitalescom.com.mx:8000/1' \\
        -e 'ENVIRONMENT=production' \\
        -p 8765:8000 \\
        --restart unless-stopped \\
        fastapi-bugsink:latest

This script is useful for Dokploy API operations (create project, set env, etc.)
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

DOKPLOY_URL = os.environ.get("DOKPLOY_URL", "http://localhost:3000/api")
DOKPLOY_API_KEY = os.environ.get(
    "DOKPLOY_API_KEY",
    "el_codiceTjIwvnnrSeFZFdcIoVhsOTOEJBaZSXKsByhGteMBdxJORtJYbESDJUAVgCUChspO",
)

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": DOKPLOY_API_KEY,
}

APP_NAME = "fastapi-bugsink"

SENTRY_DSN = (
    "http://ffc27113-eaca-40aa-b322-eef262b2e2f0"
    "@bugsink.artesanosdigitalescom.com.mx:8000/1"
)


def get_projects():
    """List all projects to find the right environmentId."""
    r = httpx.get(f"{DOKPLOY_URL}/project.all", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def create_project():
    """Create a new Dokploy project."""
    r = httpx.post(
        f"{DOKPLOY_URL}/project.create",
        headers=HEADERS,
        json={"name": APP_NAME, "description": "FastAPI with Bugsink error tracking"},
    )
    r.raise_for_status()
    return r.json()


def create_application(environment_id: str):
    """Create a new application in Dokploy."""
    r = httpx.post(
        f"{DOKPLOY_URL}/application.create",
        headers=HEADERS,
        json={"name": f"{APP_NAME}-app", "environmentId": environment_id},
    )
    r.raise_for_status()
    return r.json()


def configure_build_type(application_id: str):
    """Set build type to Dockerfile."""
    r = httpx.post(
        f"{DOKPLOY_URL}/application.saveBuildType",
        headers=HEADERS,
        json={
            "applicationId": application_id,
            "buildType": "dockerfile",
            "dockerfile": "Dockerfile",
            "dockerContextPath": "/",
            "dockerBuildStage": "",
            "herokuVersion": "24",
            "railpackVersion": "0.15.4",
        },
    )
    r.raise_for_status()
    return r.json()


def set_env_vars(application_id: str):
    """Set environment variables for the application."""
    env_content = f"SENTRY_DSN={SENTRY_DSN}\nENVIRONMENT=production\n"
    r = httpx.post(
        f"{DOKPLOY_URL}/application.saveEnvironment",
        headers=HEADERS,
        json={
            "applicationId": application_id,
            "env": env_content,
            "buildArgs": "",
            "buildSecrets": "",
            "createEnvFile": True,
        },
    )
    r.raise_for_status()
    return r.json()


def deploy(application_id: str):
    """Trigger deployment."""
    r = httpx.post(
        f"{DOKPLOY_URL}/application.deploy",
        headers=HEADERS,
        json={"applicationId": application_id},
    )
    r.raise_for_status()
    return r.json()


def main():
    print("Creating project...")
    proj = create_project()
    env_id = proj["environment"]["environmentId"]
    print(f"Project: {proj['project']['projectId']}, env: {env_id}")

    print(f"\nCreating application '{APP_NAME}'...")
    app_data = create_application(env_id)
    app_id = app_data["applicationId"]
    print(f"Created: {app_id}")

    print("\nSetting build type to Dockerfile...")
    configure_build_type(app_id)

    print("\nSetting environment variables...")
    set_env_vars(app_id)

    print("\nDeploying...")
    deploy(app_id)
    print("Deployment triggered successfully!")


if __name__ == "__main__":
    main()
