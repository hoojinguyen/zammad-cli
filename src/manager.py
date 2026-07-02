import os
import sys
import subprocess
import socket
import json
from src.utils import log_info, log_error, get_install_dir, run_command, Colors
import src.config as config

def check_env_ready():
    """Verifies that the installation directory exists and contains a .env config."""
    install_dir = get_install_dir()
    if not os.path.exists(install_dir) or not os.path.exists(os.path.join(install_dir, ".env")):
        raise RuntimeError(f"Zammad is not installed in {install_dir}. Please run 'install' first.")
    return install_dir

def start_services():
    """Starts the Docker Compose container stack."""
    install_dir = check_env_ready()
    log_info("Starting Zammad services...")
    os.chdir(install_dir)
    run_command(["docker", "compose", "up", "-d"])
    log_info("Services started successfully.")
    print_access_guide()

def stop_services():
    """Stops the Docker Compose container stack."""
    install_dir = check_env_ready()
    log_info("Stopping Zammad services...")
    os.chdir(install_dir)
    run_command(["docker", "compose", "down"])
    log_info("Services stopped successfully.")

def restart_services():
    """Restarts the Docker Compose container stack."""
    install_dir = check_env_ready()
    log_info("Restarting Zammad services...")
    os.chdir(install_dir)
    run_command(["docker", "compose", "restart"])
    log_info("Services restarted successfully.")

def get_local_ip():
    """Fetches the primary local network IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_web_port():
    """Retrieves the host port mapped to the zammad-nginx service container dynamically."""
    install_dir = get_install_dir()
    try:
        res = subprocess.run(
            ["docker", "compose", "ps", "zammad-nginx", "--format", "json"],
            cwd=install_dir, capture_output=True, text=True
        )
        if res.stdout.strip():
            try:
                data_list = json.loads(res.stdout)
                if not isinstance(data_list, list):
                    data_list = [data_list]
                for data in data_list:
                    publishers = data.get("Publishers", [])
                    for pub in publishers:
                        if pub.get("TargetPort") == 8080 and pub.get("PublishedPort"):
                            return pub.get("PublishedPort")
            except Exception:
                for line in res.stdout.splitlines():
                    data = json.loads(line)
                    publishers = data.get("Publishers", [])
                    for pub in publishers:
                        if pub.get("TargetPort") == 8080 and pub.get("PublishedPort"):
                            return pub.get("PublishedPort")
    except Exception:
        pass
    
    # Try parsing .env as fallback
    try:
        from src.db import parse_config_env
        env_config = parse_config_env()
        return int(env_config.get("NGINX_EXPOSE_PORT", config.DEFAULT_WEB_PORT))
    except Exception:
        return config.DEFAULT_WEB_PORT

def print_access_guide():
    """Prints local, LAN, and public access guides for the dashboard."""
    local_ip = get_local_ip()
    port = get_web_port()
    
    port_suffix = f":{port}" if port != 80 else ""
    
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    print(f"{Colors.BOLD}            Zammad Access Guide{Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    print(f"  Local Access:           {Colors.GREEN}http://localhost{port_suffix}{Colors.NC}")
    print(f"  Local Network (LAN/VPN): {Colors.GREEN}http://{local_ip}{port_suffix}{Colors.NC}")
    print(f"  External (Cloud VPS):   {Colors.GREEN}http://[YOUR_VPS_PUBLIC_IP]{port_suffix}{Colors.NC}")
    print(f"----------------------------------------------------")
    print(f"  Setup Instructions:")
    print(f"    - Access the URL to start the Zammad onboarding wizard.")
    print(f"    - On first run, Zammad database schemas are built in the background.")
    print(f"    - If you see a '502 Bad Gateway' error, please wait 2-5 minutes for")
    print(f"      the Ruby on Rails server to finish booting, then refresh.")
    print(f"{Colors.BOLD}===================================================={Colors.NC}\n")

def show_status():
    """Queries and displays the container status."""
    install_dir = check_env_ready()
    os.chdir(install_dir)
    
    log_info("Checking container status...")
    stdout, _ = run_command(["docker", "compose", "ps"], capture_output=True)
    
    running_count = sum(1 for line in stdout.splitlines() if "running" in line.lower() or "up" in line.lower())
    
    print(f"\n{Colors.BOLD}===================================================={Colors.NC}")
    print(f"{Colors.BOLD}            Zammad Helpdesk Service Dashboard{Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    
    if running_count > 0:
        status_text = f"{Colors.GREEN}ACTIVE ({running_count} services running){Colors.NC}"
    else:
        status_text = f"{Colors.RED}STOPPED{Colors.NC}"
        
    print(f"Overall Status: {status_text}")
    print(f"Install Dir:    {install_dir}")
    print(f"----------------------------------------------------")
    print(stdout)
    print(f"{Colors.BOLD}===================================================={Colors.NC}\n")
    if running_count > 0:
        print_access_guide()

def stream_logs(service=None, follow=False):
    """Streams container logs directly to stdout/stderr."""
    install_dir = check_env_ready()
    os.chdir(install_dir)
    
    cmd = ["docker", "compose", "logs"]
    if follow:
        cmd.append("-f")
    if service:
        cmd.append(service)
        
    log_info(f"Streaming logs for {service if service else 'all services'}... (Press Ctrl+C to exit)")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nLog streaming stopped.")
    except subprocess.CalledProcessError as e:
        log_error(f"Error displaying logs: {e}")

def health_check():
    """Runs a series of health checks on the Zammad stack."""
    install_dir = check_env_ready()
    os.chdir(install_dir)
    
    log_info("Running health checks...")
    print("")
    
    # Check if containers are running
    try:
        stdout, _ = run_command(["docker", "compose", "ps", "--format", "json"], capture_output=True)
        running = 0
        total = 0
        lines = stdout.strip().splitlines()
        for line in lines:
            if not line:
                continue
            try:
                data = json.loads(line)
                total += 1
                if data.get("State") == "running":
                    running += 1
            except Exception:
                pass
        
        if total == 0:
            stdout_raw, _ = run_command(["docker", "compose", "ps"], capture_output=True)
            for line in stdout_raw.splitlines():
                if "up" in line.lower() or "running" in line.lower():
                    running += 1
                if line.strip() and not line.startswith("NAME") and not line.startswith("-----"):
                    total += 1
                    
        print(f"{Colors.BOLD}Container Status:{Colors.NC}")
        print(f"  Running: {running} / {total}")
        print("")
    except Exception as e:
        log_error(f"Failed to check container status: {e}")
        
    # Check HTTP response
    print(f"{Colors.BOLD}Web Server Health:{Colors.NC}")
    port = get_web_port()
    try:
        import urllib.request
        import urllib.error
        url = f"http://localhost:{port}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                code = response.getcode()
                if code == 200:
                    print(f"  {Colors.GREEN}✓ Nginx is responding (HTTP {code}){Colors.NC}")
                else:
                    print(f"  {Colors.YELLOW}⚠ Nginx returned HTTP {code}{Colors.NC}")
        except urllib.error.HTTPError as e:
            print(f"  {Colors.GREEN}✓ Nginx is responding (HTTP {e.code}){Colors.NC}")
        except urllib.error.URLError as e:
            print(f"  {Colors.RED}✗ Web server is unreachable at {url}: {e.reason}{Colors.NC}")
    except Exception as e:
        print(f"  {Colors.RED}✗ Failed to connect: {e}{Colors.NC}")
    print("")
    
    # Check disk usage
    print(f"{Colors.BOLD}Docker Disk Usage:{Colors.NC}")
    try:
        stdout, _ = run_command(["docker", "system", "df"], capture_output=True)
        for line in stdout.splitlines():
            print(f"  {line}")
    except Exception as e:
        log_error(f"Failed to fetch docker disk usage: {e}")
    print("")
    
    log_info("Health check completed.")
