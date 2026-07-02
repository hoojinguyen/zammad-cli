# Zammad Helpdesk CLI Installer and Manager

This repository contains a modular Command Line Interface (CLI) tool to install, run, and manage Zammad Helpdesk on macOS and Ubuntu using Docker. 

The repository contains only the management tool source code. It downloads the official Zammad Docker Compose configuration files dynamically at runtime during the installation step.

---

## Technical Stack

The Zammad Helpdesk deployment runs as an orchestrated multi-container Docker Compose stack comprising the following components:

*   **Ruby on Rails**: The application server layer split into:
    *   `zammad-railsserver`: The main Rails web server executing the business logic.
    *   `zammad-scheduler`: Running background jobs, automation tasks, and email fetching/sending.
    *   `zammad-websocket`: Managing real-time bidirectional messaging for ticket updates.
*   **PostgreSQL**: Relational database storing tickets, users, groups, and system configuration.
*   **Elasticsearch**: Powering high-performance full-text search indexing across ticket contents and attachments.
*   **Redis**: Key-value data store used as the background queuing backend and websocket coordinator.
*   **Memcached**: Caching database queries and application sessions.
*   **Nginx Proxy**: Reverse proxy web server routing public HTTP traffic to the Rails and websocket containers.

---

## Prerequisites

- Docker Engine and Docker Compose (v2)
- Python 3
- Ubuntu Server (20.04/22.04/24.04 LTS) or macOS

---

## Installation

To clone the repository and run the installation, execute the following command on your target machine:

**On Ubuntu / Linux:**
```bash
git clone https://github.com/hoojinguyen/zammad-cli.git && cd zammad-cli && sudo ./install.sh
```

**On macOS:**
```bash
git clone https://github.com/hoojinguyen/zammad-cli.git && cd zammad-cli && ./install.sh
```

The bootstrap script automatically:
- Installs necessary system prerequisites (`curl`, `git`, `openssl`, etc.).
- Tunes and persists required host kernel limits (`vm.max_map_count=262144` for Elasticsearch).
- Installs Docker Engine and Compose plugin if missing.
- Deploys the CLI to `/opt/zammad-docker/` (on Linux) and creates a global symlink `/usr/local/bin/zammad`.
- Programmatically clones the Zammad repository, configures secure PostgreSQL credentials, checks and resolves host port collisions, and boots the microservices stack.

---

## Usage

Manage Zammad using the `zammad` CLI. The installer automatically creates a global symlink so you can run it from any directory:

```bash
zammad
```

If the global symlink is not set up, run it directly from the repository folder:
```bash
./zammad
```

Alternatively, use direct subcommands:

### Service Lifecycle & Setup Controls
- Install Zammad: `zammad install`
- Start services: `zammad start`
- Stop services: `zammad stop`
- Restart services: `zammad restart`
- Inspect service container status: `zammad status`
- Stream service logs: `zammad logs [service] [-f]` (e.g. `zammad logs -f` or `zammad logs zammad-nginx`)
- Run health checks (containers, web status, disk space): `zammad health`
- Uninstall and delete Zammad data: `zammad uninstall`

### Database Operations
- Drop into PostgreSQL `psql` interactive terminal shell: `zammad db shell`
- View database credentials and connection guide: `zammad db info`
- Export database SQL dump backup: `zammad db backup [-f file.sql]`
- Import database SQL dump backup: `zammad db restore file.sql`

### Volume Backups (Recommended)
Because Zammad stores uploads/attachments outside the database in local Docker volumes, use the `backup` subcommand group to preserve the entire state:
- Create a full volume backup (database + file uploads): `zammad backup create`
- List available backups: `zammad backup list`
- Restore volumes from backup archive: `zammad backup restore file.tar.gz`

---

## Centralized Configurations

To simplify maintenance and future updates, configurations and dependencies are centralized:
*   **System Dependencies & Kernel settings**: Located at the top of [install.sh](file:///Users/hoojinguyen/Hooji/tools/zammad/install.sh) in the `CONFIGURATION VARIABLES` section.
*   **Repository URLs & Defaults**: Located in [src/config.py](file:///Users/hoojinguyen/Hooji/tools/zammad/src/config.py) for Zammad Docker Compose git targets, default ports, and database credentials.

---

## Logs

Detailed installation and management logs are written to `zammad-install.log` in the Zammad installation directory (e.g. `/opt/zammad-docker/zammad-install.log`).
