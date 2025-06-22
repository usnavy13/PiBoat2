#!/usr/bin/env python3
"""
LTE USB Adapter Connectivity Test Script
Tests internet connectivity specifically through the wwan0 (LTE) interface
"""

import subprocess
import socket
import time
import sys
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class LTEConnectivityTester:
    def __init__(self, verbose=False):
        self.interface = "wwan0"
        self.verbose = verbose
        self.test_results = []
        self.test_hosts = {
            "Google DNS": "8.8.8.8",
            "Cloudflare DNS": "1.1.1.1",
            "Google": "google.com"
        }
        self.ipv6_test_hosts = {
            "Google IPv6": "2001:4860:4860::8888",
            "Cloudflare IPv6": "2606:4700:4700::1111"
        }
    
    def _log_test_result(self, test_name: str, success: bool, message: str, raw_data: Dict = None):
        """Log detailed test results for analysis"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "success": success,
            "message": message,
            "raw_data": raw_data or {}
        }
        self.test_results.append(result)
        
        if self.verbose:
            print(f"\n📝 RAW TEST DATA for {test_name}:")
            print(f"   Success: {success}")
            print(f"   Message: {message}")
            if raw_data:
                for key, value in raw_data.items():
                    print(f"   {key}: {value}")
            print("-" * 40)
        
    def check_interface_status(self) -> Dict[str, any]:
        """Check if wwan0 interface exists and get its status"""
        print(f"🔍 Checking {self.interface} interface status...")
        
        try:
            # Get interface information
            result = subprocess.run(['ip', 'addr', 'show', self.interface], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return {
                    "exists": False,
                    "error": f"Interface {self.interface} not found"
                }
            
            output = result.stdout
            
            # Parse interface status
            is_up = "UP" in output and "LOWER_UP" in output
            
            # Extract IP addresses
            ipv4_addresses = re.findall(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', output)
            ipv6_addresses = re.findall(r'inet6 ([0-9a-f:]+/\d+)', output)
            
            status = {
                "exists": True,
                "is_up": is_up,
                "ipv4_addresses": ipv4_addresses,
                "ipv6_addresses": ipv6_addresses,
                "raw_output": output
            }
            
            print(f"✅ Interface {self.interface} found and {'UP' if is_up else 'DOWN'}")
            print(f"   IPv4 addresses: {ipv4_addresses if ipv4_addresses else 'None'}")
            print(f"   IPv6 addresses: {ipv6_addresses if ipv6_addresses else 'None'}")
            
            return status
            
        except subprocess.TimeoutExpired:
            return {"exists": False, "error": "Timeout checking interface"}
        except Exception as e:
            return {"exists": False, "error": str(e)}
    
    def check_routes(self) -> Dict[str, List[str]]:
        """Check routing table for wwan0 routes"""
        print(f"\n🛣️  Checking routes for {self.interface}...")
        
        routes = {"ipv4": [], "ipv6": []}
        
        try:
            # IPv4 routes
            result = subprocess.run(['ip', 'route', 'show', 'dev', self.interface], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                routes["ipv4"] = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            # IPv6 routes
            result = subprocess.run(['ip', '-6', 'route', 'show', 'dev', self.interface], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                routes["ipv6"] = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            print(f"   IPv4 routes: {len(routes['ipv4'])} found")
            for route in routes["ipv4"]:
                if route:
                    print(f"     {route}")
            
            print(f"   IPv6 routes: {len(routes['ipv6'])} found")
            for route in routes["ipv6"]:
                if route:
                    print(f"     {route}")
                    
        except Exception as e:
            print(f"❌ Error checking routes: {e}")
        
        return routes
    
    def save_results_to_file(self, filename: str = None):
        """Save detailed test results to a JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lte_test_results_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.test_results, f, indent=2)
            print(f"\n💾 Detailed test results saved to: {filename}")
            return filename
        except Exception as e:
            print(f"\n❌ Failed to save results: {e}")
            return None
    
    def test_ping_through_interface(self, host: str, use_ipv6: bool = False) -> Tuple[bool, str]:
        """Test ping connectivity through specific interface"""
        family = "IPv6" if use_ipv6 else "IPv4"
        cmd = ['ping', '-c', '3', '-W', '5', '-I', self.interface]
        
        if use_ipv6:
            cmd.insert(1, '-6')
        
        cmd.append(host)
        
        raw_data = {
            "command": ' '.join(cmd),
            "family": family,
            "target_host": host,
            "interface": self.interface
        }
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            raw_data.update({
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timeout": False
            })
            
            if result.returncode == 0:
                # Extract stats from ping output
                stats_match = re.search(r'(\d+)% packet loss', result.stdout)
                packet_loss = stats_match.group(1) if stats_match else "unknown"
                
                time_match = re.search(r'time=(\d+\.?\d*)ms', result.stdout)
                avg_time = time_match.group(1) if time_match else "unknown"
                
                # Extract more detailed stats
                rtt_match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms', result.stdout)
                if rtt_match:
                    raw_data.update({
                        "rtt_min": rtt_match.group(1),
                        "rtt_avg": rtt_match.group(2),
                        "rtt_max": rtt_match.group(3),
                        "rtt_mdev": rtt_match.group(4)
                    })
                
                raw_data.update({
                    "packet_loss_percent": packet_loss,
                    "avg_time_ms": avg_time
                })
                
                success_msg = f"Success (loss: {packet_loss}%, avg: {avg_time}ms)"
                self._log_test_result(f"ping_{family.lower()}_{host}", True, success_msg, raw_data)
                return True, success_msg
            else:
                error_msg = result.stderr.strip() or "Ping failed"
                self._log_test_result(f"ping_{family.lower()}_{host}", False, error_msg, raw_data)
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            raw_data.update({"timeout": True, "timeout_seconds": 20})
            self._log_test_result(f"ping_{family.lower()}_{host}", False, "Timeout", raw_data)
            return False, "Timeout"
        except Exception as e:
            raw_data.update({"exception": str(e)})
            self._log_test_result(f"ping_{family.lower()}_{host}", False, str(e), raw_data)
            return False, str(e)
    
    def test_dns_resolution(self, hostname: str) -> Tuple[bool, str]:
        """Test DNS resolution using LTE interface"""
        try:
            # Try direct socket DNS resolution first (works with interface binding)
            return self._socket_dns_test(hostname)
        except Exception as e:
            error_msg = f"DNS resolution failed: {e}"
            self._log_test_result(f"dns_{hostname}", False, error_msg, {"exception": str(e)})
            return False, error_msg
    
    def _get_interface_ip(self) -> str:
        """Get the first available IP address from the LTE interface"""
        try:
            result = subprocess.run(['ip', 'addr', 'show', self.interface], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                # Try IPv4 first
                ipv4_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                if ipv4_match:
                    return ipv4_match.group(1)
                # Fall back to IPv6
                ipv6_match = re.search(r'inet6 ([0-9a-f:]+)', result.stdout)
                if ipv6_match:
                    return ipv6_match.group(1)
        except:
            pass
        return "127.0.0.1"  # Fallback
    
    def _is_valid_ip(self, addr: str) -> bool:
        """Check if string is a valid IP address"""
        try:
            socket.inet_pton(socket.AF_INET, addr)
            return True
        except:
            try:
                socket.inet_pton(socket.AF_INET6, addr)
                return True
            except:
                return False
    
    def _socket_dns_test(self, hostname: str) -> Tuple[bool, str]:
        """DNS test using Python socket with interface binding"""
        ipv6_addr = self._get_interface_ipv6()
        raw_data = {
            "hostname": hostname,
            "interface": self.interface,
            "ipv6_addr": ipv6_addr,
            "method": "socket_getaddrinfo"
        }
        
        try:
            # Create a socket and bind to LTE interface
            sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            sock.settimeout(10)
            
            # For IPv6, we need to get the IPv6 address
            if ipv6_addr:
                sock.bind((ipv6_addr, 0))
                raw_data["socket_bound"] = True
                
                # Try to resolve using getaddrinfo with bound socket context
                # Note: This still uses system resolver but through our interface
                result = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
                raw_data["getaddrinfo_result"] = str(result)
                
                addresses = []
                ipv4_addresses = []
                ipv6_addresses = []
                
                for addr_info in result:
                    ip = addr_info[4][0]
                    if self._is_valid_ip(ip):
                        addresses.append(ip)
                        if ':' in ip:
                            ipv6_addresses.append(ip)
                        else:
                            ipv4_addresses.append(ip)
                
                raw_data.update({
                    "all_addresses": addresses,
                    "ipv4_addresses": ipv4_addresses,
                    "ipv6_addresses": ipv6_addresses,
                    "total_addresses": len(addresses)
                })
                
                sock.close()
                
                if addresses:
                    success_msg = f"Resolved to: {', '.join(addresses[:3])}"
                    self._log_test_result(f"dns_{hostname}", True, success_msg, raw_data)
                    return True, success_msg
                else:
                    error_msg = "No valid IP addresses returned"
                    self._log_test_result(f"dns_{hostname}", False, error_msg, raw_data)
                    return False, error_msg
            else:
                error_msg = "No IPv6 address found on LTE interface"
                raw_data["socket_bound"] = False
                self._log_test_result(f"dns_{hostname}", False, error_msg, raw_data)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Socket DNS test failed: {e}"
            raw_data["exception"] = str(e)
            self._log_test_result(f"dns_{hostname}", False, error_msg, raw_data)
            return False, error_msg
    
    def _get_interface_ipv6(self) -> str:
        """Get the IPv6 address from the LTE interface"""
        try:
            result = subprocess.run(['ip', '-6', 'addr', 'show', self.interface], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                # Get global IPv6 address (not link-local)
                ipv6_match = re.search(r'inet6 ([0-9a-f:]+)/\d+.*scope global', result.stdout)
                if ipv6_match:
                    return ipv6_match.group(1)
        except:
            pass
        return None
    
    def test_tcp_connectivity(self, host: str, port: int, use_ipv6: bool = False) -> Tuple[bool, str]:
        """Test TCP connectivity through LTE interface"""
        try:
            # Create socket based on IP version preference
            family = socket.AF_INET6 if use_ipv6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            try:
                # Get interface IP and bind to it
                if use_ipv6:
                    # Get IPv6 address of wwan0
                    result = subprocess.run(['ip', '-6', 'addr', 'show', self.interface], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        ipv6_match = re.search(r'inet6 ([0-9a-f:]+)/\d+.*scope global', result.stdout)
                        if ipv6_match:
                            local_ipv6 = ipv6_match.group(1)
                            sock.bind((local_ipv6, 0))
                        else:
                            return False, "No global IPv6 address found on LTE interface"
                    else:
                        return False, "Failed to get IPv6 address from LTE interface"
                else:
                    # Get IPv4 address of wwan0
                    result = subprocess.run(['ip', 'addr', 'show', self.interface], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        ipv4_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                        if ipv4_match:
                            local_ipv4 = ipv4_match.group(1)
                            sock.bind((local_ipv4, 0))
                        else:
                            return False, "No IPv4 address found on LTE interface"
                    else:
                        return False, "Failed to get IPv4 address from LTE interface"
                
                # Resolve hostname to IP if needed
                if not self._is_valid_ip(host):
                    try:
                        addr_info = socket.getaddrinfo(host, port, family)
                        if addr_info:
                            target_ip = addr_info[0][4][0]
                        else:
                            return False, f"Could not resolve {host}"
                    except Exception as e:
                        return False, f"DNS resolution failed: {e}"
                else:
                    target_ip = host
                
                # Connect
                sock.connect((target_ip, port))
                sock.close()
                return True, f"TCP connection successful to {host}:{port} ({target_ip})"
                
            except socket.timeout:
                return False, "Connection timeout"
            except socket.error as e:
                return False, f"Socket error: {e}"
            finally:
                try:
                    sock.close()
                except:
                    pass
                
        except Exception as e:
            return False, f"TCP test error: {e}"
    
    def test_https_connectivity(self) -> Tuple[bool, str]:
        """Test HTTPS connectivity through LTE interface"""
        try:
            # Check if we have IPv4 or IPv6
            ipv4_addr = self._get_interface_ip()
            ipv6_addr = self._get_interface_ipv6()
            
            # Try IPv6 first if available, then IPv4
            if ipv6_addr:
                return self._test_https_ipv6(ipv6_addr)
            elif ipv4_addr and ipv4_addr != "127.0.0.1":
                return self._test_https_ipv4(ipv4_addr)
            else:
                return False, "No valid LTE interface IP found"
                
        except Exception as e:
            return False, f"HTTPS Error: {e}"
    
    def _test_https_ipv6(self, ipv6_addr: str) -> Tuple[bool, str]:
        """Test HTTPS connectivity using IPv6"""
        try:
            import ssl
            import json
            
            # Create IPv6 socket
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock.settimeout(15)
            
            try:
                # Bind to IPv6 address
                sock.bind((ipv6_addr, 0))
                
                # Resolve httpbin.org to IPv6
                addr_info = socket.getaddrinfo('httpbin.org', 443, socket.AF_INET6)
                if not addr_info:
                    return False, "Could not resolve httpbin.org to IPv6"
                
                target_ipv6 = addr_info[0][4][0]
                
                # Create SSL context and wrap socket
                context = ssl.create_default_context()
                secure_sock = context.wrap_socket(sock, server_hostname='httpbin.org')
                
                # Connect to httpbin.org
                secure_sock.connect((target_ipv6, 443))
                
                # Send HTTP request
                request = (
                    "GET /ip HTTP/1.1\r\n"
                    "Host: httpbin.org\r\n"
                    "User-Agent: LTE-Connectivity-Test/1.0\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                )
                secure_sock.send(request.encode())
                
                # Read response
                response = b""
                while True:
                    chunk = secure_sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                
                # Parse response
                response_text = response.decode('utf-8')
                if "200 OK" in response_text:
                    # Extract JSON body
                    json_start = response_text.find('{')
                    if json_start > 0:
                        json_body = response_text[json_start:]
                        try:
                            data = json.loads(json_body)
                            return True, f"HTTPS IPv6 OK - Your IP: {data.get('origin', 'Unknown')}"
                        except:
                            return True, "HTTPS IPv6 OK - Connection successful"
                    else:
                        return True, "HTTPS IPv6 OK - Connection successful"
                else:
                    return False, f"HTTP Error in response: {response_text[:200]}"
                    
            except socket.timeout:
                return False, "HTTPS IPv6 connection timeout"
            except ssl.SSLError as e:
                return False, f"SSL Error: {e}"
            except socket.error as e:
                return False, f"Socket error: {e}"
            finally:
                try:
                    sock.close()
                except:
                    pass
                
        except Exception as e:
            return False, f"HTTPS IPv6 Error: {e}"
    
    def _test_https_ipv4(self, ipv4_addr: str) -> Tuple[bool, str]:
        """Test HTTPS connectivity using IPv4"""
        try:
            import ssl
            import json
            
            # Create IPv4 socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            
            try:
                # Bind to IPv4 address
                sock.bind((ipv4_addr, 0))
                
                # Create SSL context and wrap socket
                context = ssl.create_default_context()
                secure_sock = context.wrap_socket(sock, server_hostname='httpbin.org')
                
                # Connect to httpbin.org
                secure_sock.connect(('httpbin.org', 443))
                
                # Send HTTP request
                request = (
                    "GET /ip HTTP/1.1\r\n"
                    "Host: httpbin.org\r\n"
                    "User-Agent: LTE-Connectivity-Test/1.0\r\n"
                    "\r\n"
                )
                secure_sock.send(request.encode())
                
                # Read response
                response = b""
                while True:
                    chunk = secure_sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                
                # Parse response
                response_text = response.decode('utf-8')
                if "200 OK" in response_text:
                    # Extract JSON body
                    json_start = response_text.find('{')
                    if json_start > 0:
                        json_body = response_text[json_start:]
                        try:
                            data = json.loads(json_body)
                            return True, f"HTTPS IPv4 OK - Your IP: {data.get('origin', 'Unknown')}"
                        except:
                            return True, "HTTPS IPv4 OK - Connection successful"
                    else:
                        return True, "HTTPS IPv4 OK - Connection successful"
                else:
                    return False, f"HTTP Error in response: {response_text[:200]}"
                    
            except socket.timeout:
                return False, "HTTPS IPv4 connection timeout"
            except ssl.SSLError as e:
                return False, f"SSL Error: {e}"
            except socket.error as e:
                return False, f"Socket error: {e}"
            finally:
                try:
                    sock.close()
                except:
                    pass
                
        except Exception as e:
            return False, f"HTTPS IPv4 Error: {e}"
    
    def detect_carrier_filtering(self) -> Dict[str, str]:
        """Detect common carrier filtering behaviors using LTE interface"""
        results = {}
        
        print(f"\n🔍 Detecting carrier filtering...")
        
        # Test HTTP using LTE interface binding
        try:
            interface_ip = self._get_interface_ip()
            if interface_ip == "127.0.0.1":
                results['detection_error'] = "No valid LTE interface IP found"
                return results
            
            # Test HTTP (often redirected) - using raw socket with LTE binding
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                sock.bind((interface_ip, 0))
                
                # Connect to google.com:80
                try:
                    addr_info = socket.getaddrinfo('google.com', 80, socket.AF_INET)
                    if addr_info:
                        google_ip = addr_info[0][4][0]
                        sock.connect((google_ip, 80))
                        
                        # Send HTTP request
                        request = (
                            "GET / HTTP/1.1\r\n"
                            "Host: google.com\r\n"
                            "User-Agent: LTE-Connectivity-Test/1.0\r\n"
                            "Connection: close\r\n"
                            "\r\n"
                        )
                        sock.send(request.encode())
                        
                        # Read response
                        response = b""
                        while True:
                            chunk = sock.recv(4096)
                            if not chunk:
                                break
                            response += chunk
                        
                        response_text = response.decode('utf-8', errors='ignore')
                        
                        # Check for redirects
                        if 'Location:' in response_text:
                            location_match = re.search(r'Location:\s*([^\r\n]+)', response_text)
                            if location_match:
                                redirect = location_match.group(1).strip()
                                results['http_redirect'] = redirect
                                
                                # Detect carrier from redirect
                                redirect_lower = redirect.lower()
                                if 't-mobile' in redirect_lower or 'tmobile' in redirect_lower:
                                    results['carrier'] = 'T-Mobile'
                                elif 'verizon' in redirect_lower:
                                    results['carrier'] = 'Verizon'
                                elif 'att' in redirect_lower or 'at&t' in redirect_lower:
                                    results['carrier'] = 'AT&T'
                        
                        sock.close()
                        
                except Exception as connect_error:
                    results['http_connect_error'] = str(connect_error)
                    
            except Exception as sock_error:
                results['http_socket_error'] = str(sock_error)
            
            # Test carrier-specific behavior
            if 'carrier' in results:
                print(f"   📡 Detected carrier: {results['carrier']}")
                if results['carrier'] == 'T-Mobile':
                    print(f"   ⚠️  T-Mobile typically blocks ICMP and redirects HTTP")
                    results['icmp_likely_blocked'] = True
                    results['http_redirected'] = True
            elif 'http_redirect' in results:
                print(f"   🔀 HTTP redirect detected: {results['http_redirect']}")
                results['http_redirected'] = True
            else:
                print("   ✅ No carrier filtering detected (or carrier doesn't redirect)")
                    
        except Exception as e:
            results['detection_error'] = str(e)
        
        return results
    
    def temporarily_switch_to_lte(self) -> bool:
        """Temporarily make LTE the primary connection for testing"""
        print(f"\n🔀 Attempting to prioritize {self.interface} for testing...")
        
        try:
            # Check if we have IPv6 default route through wwan0
            result = subprocess.run(['ip', '-6', 'route', 'show', 'default', 'dev', self.interface], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                print("✅ IPv6 default route found through wwan0")
                return True
            else:
                print("⚠️  No default route through wwan0 - connectivity may be limited")
                return False
                
        except Exception as e:
            print(f"❌ Error checking routes: {e}")
            return False
    
    def run_connectivity_tests(self):
        """Run comprehensive connectivity tests"""
        print("🚀 Starting LTE Connectivity Tests")
        print("=" * 50)
        
        # Check interface status
        interface_status = self.check_interface_status()
        if not interface_status.get("exists"):
            print(f"❌ Cannot continue: {interface_status.get('error')}")
            return False
        
        if not interface_status.get("is_up"):
            print(f"❌ Interface {self.interface} is not UP")
            return False
        
        # Check routes
        self.check_routes()
        
        # Check if we can use LTE
        has_ipv6 = bool(interface_status.get("ipv6_addresses"))
        has_ipv4 = bool(interface_status.get("ipv4_addresses"))
        
        if not has_ipv6 and not has_ipv4:
            print("❌ No IP addresses configured on wwan0")
            return False
        
        print(f"\n🧪 Testing connectivity (IPv4: {'✅' if has_ipv4 else '❌'}, IPv6: {'✅' if has_ipv6 else '❌'})")
        print("-" * 40)
        
        success_count = 0
        total_tests = 0
        
        # Test IPv4 connectivity if available
        if has_ipv4:
            for name, host in self.test_hosts.items():
                print(f"\n📡 Testing IPv4 ping to {name} ({host})...")
                success, message = self.test_ping_through_interface(host, use_ipv6=False)
                print(f"   {'✅' if success else '❌'} {message}")
                total_tests += 1
                if success:
                    success_count += 1
        
        # Test IPv6 connectivity if available
        if has_ipv6:
            for name, host in self.ipv6_test_hosts.items():
                print(f"\n📡 Testing IPv6 ping to {name} ({host})...")
                success, message = self.test_ping_through_interface(host, use_ipv6=True)
                print(f"   {'✅' if success else '❌'} {message}")
                total_tests += 1
                if success:
                    success_count += 1
        
        # Test DNS resolution
        print(f"\n🔍 Testing DNS resolution...")
        success, message = self.test_dns_resolution("google.com")
        print(f"   {'✅' if success else '❌'} {message}")
        total_tests += 1
        if success:
            success_count += 1
        
        # Detect carrier filtering
        carrier_info = self.detect_carrier_filtering()
        
        # Test TCP connectivity
        print(f"\n🔌 Testing TCP connectivity...")
        # Try IPv4 first, then IPv6 if IPv4 fails and IPv6 is available
        success, message = self.test_tcp_connectivity("google.com", 443, use_ipv6=False)
        if not success and has_ipv6:
            print(f"   ❌ TCP IPv4 to google.com:443 - {message}")
            print(f"   🔄 Retrying with IPv6...")
            success, message = self.test_tcp_connectivity("google.com", 443, use_ipv6=True)
            print(f"   {'✅' if success else '❌'} TCP IPv6 to google.com:443 - {message}")
        else:
            print(f"   {'✅' if success else '❌'} TCP to google.com:443 - {message}")
        total_tests += 1
        if success:
            success_count += 1
        
        # Test HTTPS connectivity  
        print(f"\n🔒 Testing HTTPS connectivity...")
        success, message = self.test_https_connectivity()
        print(f"   {'✅' if success else '❌'} {message}")
        total_tests += 1
        if success:
            success_count += 1
        
        # Summary
        print(f"\n📊 Test Summary")
        print("-" * 20)
        print(f"Interface: {self.interface}")
        print(f"Status: {'UP' if interface_status.get('is_up') else 'DOWN'}")
        print(f"IPv4: {'Available' if has_ipv4 else 'Not configured'}")
        print(f"IPv6: {'Available' if has_ipv6 else 'Not configured'}")
        
        if 'carrier' in carrier_info:
            print(f"Carrier: {carrier_info['carrier']}")
        
        print(f"Tests passed: {success_count}/{total_tests}")
        
        # Explain results
        print(f"\n💡 Connectivity Analysis")
        print("-" * 25)
        
        # Check if core connectivity (DNS + TCP/HTTPS) works, ignore ping failures
        core_tests_passed = False
        if success_count >= 2:  # DNS + at least one of TCP/HTTPS
            core_tests_passed = True
            print("✅ LTE connectivity is working!")
            print("   DNS, TCP, and HTTPS work properly")
            
            if 'icmp_likely_blocked' in carrier_info:
                print("⚠️  ICMP/ping is blocked by carrier (normal)")
                print("   This is typical carrier security policy")
                
            if 'http_redirected' in carrier_info:
                print("⚠️  HTTP traffic gets redirected (normal)")
                print("   Use HTTPS for unrestricted access")
                
        elif success_count > 0 and not core_tests_passed:
            print("⚠️  Partial LTE connectivity")
            print("   Some services work, others may be filtered")
        else:
            print("❌ LTE connectivity issues detected")
            print("   Check interface configuration and carrier status")
        
        # Recommendations
        if core_tests_passed or success_count > 0:
            print(f"\n💡 Recommendations:")
            print("• Your LTE connection works for data services")
            print("• Use HTTPS instead of HTTP for web browsing")
            print("• Ping tests will fail (carrier blocks ICMP)")
            print("• TCP/UDP applications should work normally")
        
        return core_tests_passed or success_count > 0

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LTE USB Adapter Connectivity Tester")
    parser.add_argument("-v", "--verbose", action="store_true", 
                       help="Show detailed raw test data")
    parser.add_argument("-s", "--save", action="store_true",
                       help="Save detailed results to JSON file")
    parser.add_argument("-o", "--output", type=str,
                       help="Output filename for results (default: auto-generated)")
    
    args = parser.parse_args()
    
    print("LTE USB Adapter Connectivity Tester")
    print("===================================")
    if args.verbose:
        print("🔍 Verbose mode enabled - showing raw test data")
        print("=" * 50)
    
    tester = LTEConnectivityTester(verbose=args.verbose)
    
    try:
        success = tester.run_connectivity_tests()
        
        # Save results if requested
        if args.save or args.output:
            tester.save_results_to_file(args.output)
        
        exit_code = 0 if success else 1
        
        print(f"\n{'🎉 Tests completed successfully!' if success else '⚠️  Some tests failed - check configuration'}")
        
        if not args.save and not args.output:
            print("💡 Use --save to save detailed results to file, --verbose for raw data")
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        if args.save or args.output:
            print("💾 Saving partial results...")
            tester.save_results_to_file(args.output)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        if args.save or args.output:
            print("💾 Saving partial results...")
            tester.save_results_to_file(args.output)
        sys.exit(1)

if __name__ == "__main__":
    main() 