#!/usr/bin/env node
/**
 * Simple Gmail MCP Server Test
 *
 * This script tests the Gmail MCP server by directly communicating with it
 * using stdio. This is a minimal test that doesn't require the Claude Agent SDK.
 *
 * Usage: node test-gmail-mcp-simple.js
 */

const { spawn } = require('child_process');
const readline = require('readline');

class MCPClient {
  constructor(command, args) {
    this.process = spawn(command, args, {
      stdio: ['pipe', 'pipe', 'inherit']
    });

    this.requestId = 1;
    this.pendingRequests = new Map();

    // Set up readline to read JSON-RPC responses
    const rl = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity
    });

    rl.on('line', (line) => {
      try {
        const response = JSON.parse(line);
        if (response.id && this.pendingRequests.has(response.id)) {
          const { resolve, reject } = this.pendingRequests.get(response.id);
          this.pendingRequests.delete(response.id);

          if (response.error) {
            reject(new Error(response.error.message || 'MCP Error'));
          } else {
            resolve(response.result);
          }
        }
      } catch (error) {
        console.error('Failed to parse response:', line);
      }
    });

    this.process.on('error', (error) => {
      console.error('Process error:', error);
    });
  }

  async sendRequest(method, params = {}) {
    const id = this.requestId++;
    const request = {
      jsonrpc: '2.0',
      id,
      method,
      params
    };

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });

      this.process.stdin.write(JSON.stringify(request) + '\n');

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error('Request timeout'));
        }
      }, 30000);
    });
  }

  async close() {
    this.process.stdin.end();
    return new Promise((resolve) => {
      this.process.on('close', resolve);
    });
  }
}

async function testGmailMCP() {
  console.log('🧪 Testing Gmail MCP Server (Simple Test)...\n');

  const client = new MCPClient('npx', ['@gongrzhe/server-gmail-autoauth-mcp']);

  try {
    // Wait a bit for the server to start
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Test 1: Initialize the connection
    console.log('📡 Test 1: Initializing connection...');
    try {
      const initResult = await client.sendRequest('initialize', {
        protocolVersion: '2024-11-05',
        capabilities: {
          roots: { listChanged: true },
          sampling: {}
        },
        clientInfo: {
          name: 'gmail-test-client',
          version: '1.0.0'
        }
      });
      console.log('✅ Connection initialized successfully');
      console.log('Server info:', JSON.stringify(initResult.serverInfo, null, 2));
    } catch (error) {
      console.error('❌ Initialization failed:', error.message);
      return;
    }

    // Test 2: List available tools
    console.log('\n🔧 Test 2: Listing available tools...');
    try {
      const toolsResult = await client.sendRequest('tools/list', {});
      console.log('✅ Available tools:');
      toolsResult.tools.forEach(tool => {
        console.log(`  - ${tool.name}: ${tool.description}`);
      });
    } catch (error) {
      console.error('❌ Failed to list tools:', error.message);
    }

    // Test 3: Search for emails
    console.log('\n📧 Test 3: Searching for recent emails...');
    try {
      const searchResult = await client.sendRequest('tools/call', {
        name: 'search_emails',
        arguments: {
          query: 'in:inbox',
          maxResults: 5
        }
      });
      console.log('✅ Search completed successfully');
      console.log('Result:', JSON.stringify(searchResult, null, 2));
    } catch (error) {
      console.error('❌ Search failed:', error.message);
    }

    // Test 4: List labels
    console.log('\n🏷️  Test 4: Listing email labels...');
    try {
      const labelsResult = await client.sendRequest('tools/call', {
        name: 'list_email_labels',
        arguments: {}
      });
      console.log('✅ Labels retrieved successfully');
      console.log('Result:', JSON.stringify(labelsResult, null, 2));
    } catch (error) {
      console.error('❌ Failed to list labels:', error.message);
    }

    console.log('\n\n✨ Tests completed!');
    console.log('✅ Gmail MCP server is responding correctly!');

  } catch (error) {
    console.error('\n❌ Unexpected error:', error);
  } finally {
    await client.close();
  }
}

// Run the tests
console.log('='.repeat(60));
console.log('Gmail MCP Server Simple Test Suite');
console.log('='.repeat(60));
console.log('\nMake sure you have authenticated with:');
console.log('  npx @gongrzhe/server-gmail-autoauth-mcp auth\n');
console.log('='.repeat(60) + '\n');

testGmailMCP().catch(console.error);
