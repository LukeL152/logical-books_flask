# Production Server Security Checklist

This checklist outlines the essential security measures to take when deploying the Logical Books application to a public-facing production server.

---

### 1. System & Software Updates
- [ ] **Host System:** The Proxmox host OS is fully updated. (`apt update && apt upgrade`)
- [ ] **Guest Systems:** All Debian VMs and Containers (Nginx, Logical Books, etc.) are fully updated.
- [ ] **Nginx:** The Nginx version is recent and patched for known vulnerabilities.
- [ ] **Application Dependencies:** All Python packages in `requirements.txt` are up-to-date and audited for vulnerabilities.

### 2. Network & Firewall Configuration
- [ ] **Port Forwarding:** Only necessary ports (typically 80 and 443) are forwarded from the router to the Nginx proxy.
- [ ] **Host Firewall (Proxmox):** A firewall is active on the Proxmox host, restricting traffic between VMs/containers and the outside world.
- [ ] **Guest Firewalls (Debian):** A firewall (e.g., `ufw`) is active on each VM and container, configured with a "deny by default" policy.
- [ ] **Virtual Networking (Proxmox):** The virtual network is segmented. The Nginx proxy can only communicate with the Logical Books VM on its application port (e.g., 5000), not with other services like the VPN.

### 3. Nginx Hardening
- [ ] **SSL/TLS:** A valid, trusted SSL certificate is installed (e.g., from Let's Encrypt).
- [ ] **SSL/TLS Configuration:** The server is configured to use strong, modern TLS protocols and ciphers. (Test with [Qualys SSL Labs](https://www.ssllabs.com/ssltest/)).
- [ ] **HTTP to HTTPS Redirect:** All traffic to port 80 is permanently redirected (301) to HTTPS on port 443.
- [ ] **Security Headers:** The Nginx configuration adds security headers to responses (`Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`).
- [ ] **Hide Server Version:** The `server_tokens off;` directive is used in `nginx.conf` to prevent version disclosure.

### 4. Intrusion Detection & Monitoring
- [ ] **`fail2ban`:** `fail2ban` is installed and configured to monitor Nginx logs (and SSH logs) and block malicious IPs.
- [ ] **Log Review:** A process is in place to regularly review Nginx and application logs for suspicious activity.

### 5. Application Security
- [ ] **Secrets Management:** All secrets (Flask `SECRET_KEY`, database passwords, Plaid API keys) are managed via environment variables or a secure vault, not hardcoded in the source code.
- [ ] **Input Validation:** The Flask application validates and sanitizes all user input to prevent vulnerabilities like SQL Injection and XSS. (This is an ongoing development task).

---
