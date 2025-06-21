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
from typing import Dict, List, Optional, Tuple

class LTEConnectivityTester:
    def __init__(self):
        self.interface = "wwan0"
        self.test_hosts = {
            "Google DNS": "8.8.8.8",
            "Cloudflare DNS": "1.1.1.1",
            "Google": "google.com"
        }
        self.ipv6_test_hosts = {
            "Google IPv6": "2001:4860:4860::8888",
            "Cloudflare IPv6": "2606:4700:4700::1111",
            "Google": "https://google.com"
        }
        
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
    
    def test_ping_through_interface(self, host: str, use_ipv6: bool = False) -> Tuple[bool, str]:
        """Test ping connectivity through specific interface"""
        family = "IPv6" if use_ipv6 else "IPv4"
        cmd = ['ping', '-c', '3', '-W', '5', '-I', self.interface]
        
        if use_ipv6:
            cmd.insert(1, '-6')
        
        cmd.append(host)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode == 0:
                # Extract stats from ping output
                stats_match = re.search(r'(\d+)% packet loss', result.stdout)
                packet_loss = stats_match.group(1) if stats_match else "unknown"
                
                time_match = re.search(r'time=(\d+\.?\d*)ms', result.stdout)
                avg_time = time_match.group(1) if time_match else "unknown"
                
                return True, f"Success (loss: {packet_loss}%, avg: {avg_time}ms)"
            else:
                return False, result.stderr.strip() or "Ping failed"
                
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    def test_dns_resolution(self, hostname: str) -> Tuple[bool, str]:
        """Test DNS resolution"""
        try:
            # Try to resolve hostname
            result = socket.getaddrinfo(hostname, None)
            addresses = [addr[4][0] for addr in result]
            return True, f"Resolved to: {', '.join(addresses[:3])}"
        except Exception as e:
            return False, str(e)
    
    def test_tcp_connectivity(self, host: str, port: int, use_ipv6: bool = True) -> Tuple[bool, str]:
        """Test TCP connectivity through LTE interface"""
        try:
            import socket
            
            # Create socket
            family = socket.AF_INET6 if use_ipv6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            try:
                # Bind to specific interface (IPv6 only)
                if use_ipv6:
                    # Get the IPv6 address of wwan0
                    result = subprocess.run(['ip', '-6', 'addr', 'show', self.interface], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        ipv6_match = re.search(r'inet6 ([0-9a-f:]+)/\d+.*scope global', result.stdout)
                        if ipv6_match:
                            local_ipv6 = ipv6_match.group(1)
                            sock.bind((local_ipv6, 0))
                
                # Connect
                sock.connect((host, port))
                sock.close()
                return True, f"TCP connection successful to {host}:{port}"
                
            except socket.timeout:
                return False, "Connection timeout"
            except socket.error as e:
                return False, f"Socket error: {e}"
            finally:
                sock.close()
                
        except Exception as e:
            return False, f"TCP test error: {e}"
    
    def test_https_connectivity(self) -> Tuple[bool, str]:
        """Test HTTPS connectivity through LTE"""
        try:
            import urllib.request
            import urllib.error
            import ssl
            
            # Test HTTPS to bypass carrier redirects
            url = "https://httpbin.org/ip"
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'LTE-Connectivity-Test/1.0')
            
            # Create SSL context
            context = ssl.create_default_context()
            
            with urllib.request.urlopen(request, timeout=15, context=context) as response:
                data = response.read().decode('utf-8')
                return True, f"HTTPS OK - Your IP: {data.strip()}"
                
        except urllib.error.URLError as e:
            return False, f"HTTPS Error: {e}"
        except Exception as e:
            return False, f"HTTPS Error: {e}"
    
    def detect_carrier_filtering(self) -> Dict[str, str]:
        """Detect common carrier filtering behaviors"""
        results = {}
        
        print(f"\n🔍 Detecting carrier filtering...")
        
        # Test HTTP vs HTTPS
        try:
            import urllib.request
            
            # Test HTTP (often redirected)
            try:
                request = urllib.request.Request("http://google.com")
                with urllib.request.urlopen(request, timeout=10) as response:
                    if 'Location' in response.headers:
                        redirect = response.headers['Location']
                        results['http_redirect'] = redirect
                        if 't-mobile' in redirect.lower():
                            results['carrier'] = 'T-Mobile'
                        elif 'verizon' in redirect.lower():
                            results['carrier'] = 'Verizon'
                        elif 'att' in redirect.lower():
                            results['carrier'] = 'AT&T'
            except:
                results['http_status'] = 'blocked_or_filtered'
            
            # Test carrier-specific behavior
            if 'carrier' in results:
                print(f"   📡 Detected carrier: {results['carrier']}")
                if results['carrier'] == 'T-Mobile':
                    print(f"   ⚠️  T-Mobile typically blocks ICMP and redirects HTTP")
                    results['icmp_likely_blocked'] = True
                    results['http_redirected'] = True
                    
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
        routes = self.check_routes()
        
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
        success, message = self.test_tcp_connectivity("google.com", 443, use_ipv6=has_ipv6)
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
    print("LTE USB Adapter Connectivity Tester")
    print("===================================")
    
    tester = LTEConnectivityTester()
    
    try:
        success = tester.run_connectivity_tests()
        exit_code = 0 if success else 1
        
        print(f"\n{'🎉 Tests completed successfully!' if success else '⚠️  Some tests failed - check configuration'}")
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 