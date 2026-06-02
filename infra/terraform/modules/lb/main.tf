# Global external HTTPS LB -> single app VM. TLS terminates here; nginx on the VM
# serves :80 and trusts the Google front-end CIDRs for X-Forwarded-*.
resource "google_compute_global_address" "lb" {
  name = "buscasam-lb"
}

resource "google_compute_health_check" "app" {
  name = "buscasam-app"
  http_health_check {
    port         = 80
    request_path = "/healthz"
  }
}

resource "google_compute_backend_service" "app" {
  name                  = "buscasam-app"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  health_checks         = [google_compute_health_check.app.id]
  backend {
    group = var.instance_group
  }
}

resource "google_compute_url_map" "https" {
  name            = "buscasam-https"
  default_service = google_compute_backend_service.app.id
}

# Google-managed cert. Goes ACTIVE only after server_name resolves to the LB IP.
resource "google_compute_managed_ssl_certificate" "app" {
  name = "buscasam"
  managed {
    domains = [var.server_name]
  }
}

resource "google_compute_target_https_proxy" "app" {
  name             = "buscasam-https"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.app.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "buscasam-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.app.id
}

# :80 -> :443 redirect.
resource "google_compute_url_map" "redirect" {
  name = "buscasam-redirect"
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "buscasam-redirect"
  url_map = google_compute_url_map.redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "buscasam-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.id
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
}
