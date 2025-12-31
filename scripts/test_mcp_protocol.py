#!/usr/bin/env python3
"""
Test if the MCP server responds to MCP protocol messages correctly.
This simulates what Claude Desktop/Code does when it tries to use the server.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
SERVER_PATH = PROJECT_ROOT / "mcp_server" / "server.py"

async def test_mcp_protocol():
    """Test MCP initialization handshake."""
    print("🧪 Testing MCP Protocol Communication\n")
    print("=" * 60)

    # Start the MCP server
    print("Starting MCP server...")
    process = await asyncio.create_subprocess_exec(
        "python3",
        str(SERVER_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    print("✓ Server process started\n")

    # Send MCP initialization message
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }

    print("Sending initialize request...")
    print(json.dumps(init_request, indent=2))
    print()

    # Send the request
    request_bytes = (json.dumps(init_request) + "\n").encode()
    process.stdin.write(request_bytes)
    await process.stdin.drain()

    # Wait for response (with timeout)
    try:
        response_line = await asyncio.wait_for(
            process.stdout.readline(),
            timeout=5.0
        )

        if response_line:
            response = json.loads(response_line)
            print("✓ Received response:")
            print(json.dumps(response, indent=2))
            print()

            # Check if it's a valid initialize response
            if "result" in response:
                server_info = response["result"].get("serverInfo", {})
                capabilities = response["result"].get("capabilities", {})

                print("✅ SUCCESS! MCP server is responding correctly")
                print(f"\nServer: {server_info.get('name')} v{server_info.get('version')}")
                print(f"Capabilities: {list(capabilities.keys())}")

                # Send initialized notification (required by MCP protocol)
                print("\n" + "=" * 60)
                print("Sending 'initialized' notification...")
                initialized_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                notification_bytes = (json.dumps(initialized_notification) + "\n").encode()
                process.stdin.write(notification_bytes)
                await process.stdin.drain()
                print("✓ Notification sent")

                # Now try to list tools
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list"
                }

                print("\n" + "=" * 60)
                print("Requesting tools list...")

                request_bytes = (json.dumps(tools_request) + "\n").encode()
                process.stdin.write(request_bytes)
                await process.stdin.drain()

                tools_response_line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=5.0
                )

                if tools_response_line:
                    tools_response = json.loads(tools_response_line)
                    print("✓ Tools response:")
                    print(json.dumps(tools_response, indent=2))

                    if "result" in tools_response:
                        tools = tools_response["result"].get("tools", [])
                        print(f"\n✅ Found {len(tools)} tools:")
                        for tool in tools:
                            print(f"  • {tool['name']}: {tool.get('description', 'No description')}")

                        return True
                else:
                    print("❌ No tools response received")
                    return False
            else:
                print("❌ Invalid response - missing 'result' field")
                return False
        else:
            print("❌ No response received from server")

            # Check stderr for errors
            stderr = await process.stderr.read()
            if stderr:
                print("\nServer errors:")
                print(stderr.decode())

            return False

    except asyncio.TimeoutError:
        print("❌ Timeout waiting for server response")

        # Check stderr for errors
        try:
            stderr = await asyncio.wait_for(process.stderr.read(), timeout=1.0)
            if stderr:
                print("\nServer errors:")
                print(stderr.decode())
        except (asyncio.TimeoutError, Exception) as e:
            # Ignore errors when trying to read stderr during cleanup
            pass

        return False
    finally:
        # Clean up
        process.terminate()
        await process.wait()

if __name__ == "__main__":
    success = asyncio.run(test_mcp_protocol())
    sys.exit(0 if success else 1)
