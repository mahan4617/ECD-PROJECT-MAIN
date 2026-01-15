import re
import time
import urllib.parse
from django.conf import settings
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)

class FirewallMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # 1. IP Blocking
        ip = self.get_client_ip(request)
        blocked_ips = getattr(settings, 'FIREWALL_BLOCKED_IPS', [])
        if ip in blocked_ips:
            logger.warning(f"Firewall blocked IP: {ip}")
            return HttpResponseForbidden("Access Denied by Firewall (IP Blocked)")

        # 2. Rate Limiting (Simple Token Bucket or Counter)
        # Limit: 100 requests per minute by default
        rate_limit = getattr(settings, 'FIREWALL_RATE_LIMIT', 100)
        if rate_limit > 0:
            cache_key = f"firewall_rate_limit_{ip}"
            request_count = cache.get(cache_key, 0)
            if request_count >= rate_limit:
                logger.warning(f"Firewall rate limit exceeded for IP: {ip}")
                return HttpResponseForbidden("Too Many Requests (Rate Limit Exceeded)")
            cache.set(cache_key, request_count + 1, timeout=60)

        # 3. Basic SQL Injection / XSS Detection
        # Check query parameters and path
        suspicious_patterns = [
            r"(\%27)|(\')",  # Single quote
            r"(\-\-)",       # Comment
            r"(\%23)|(#)",   # Comment
            r"(xp_)",        # XP_ cmds
            r"(;)",          # Semicolon
            r"(<script)",    # XSS
            r"(javascript:)", # XSS
            r"(UNION\s+SELECT)", # SQLi (with space check)
        ]
        
        # Check Path (Unquoted)
        path = urllib.parse.unquote(request.path)
        for pattern in suspicious_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                logger.warning(f"Firewall blocked suspicious path: {request.path} from IP: {ip}")
                return HttpResponseForbidden("Malicious Request Detected")

        # Check Query Params (Unquoted)
        query_string = request.META.get('QUERY_STRING', '')
        if query_string:
            decoded_query = urllib.parse.unquote(query_string)
            for pattern in suspicious_patterns:
                if re.search(pattern, decoded_query, re.IGNORECASE):
                    logger.warning(f"Firewall blocked suspicious query: {query_string} from IP: {ip}")
                    return HttpResponseForbidden("Malicious Request Detected")

        return None

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
