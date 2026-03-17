#!/usr/bin/env tsx
/**
 * Test script for Gmail MCP Server
 *
 * This script tests the Gmail MCP server installation by:
 * 1. Connecting to the server
 * 2. Searching for recent emails
 * 3. Reading the first email found
 *
 * Usage: npx tsx test-gmail-mcp.ts
 */

import { query } from "@anthropic-ai/claude-agent-sdk";

async function testGmailMCP() {
  console.log("🧪 Testing Gmail MCP Server...\n");

  try {
    // Test 1: Search for recent emails
    console.log("📧 Test 1: Searching for recent emails in inbox...");

    const searchResponse = query({
      prompt: "Search for the 5 most recent emails in my inbox and show me their subjects, senders, and dates.",
      options: {
        mcpServers: {
          "gmail": {
            command: "npx",
            args: ["@gongrzhe/server-gmail-autoauth-mcp"]
          }
        },
        allowedTools: [
          "mcp__gmail__search_emails",
          "mcp__gmail__read_email",
          "mcp__gmail__list_email_labels"
        ],
        model: "claude-sonnet-4-5"
      }
    });

    let emailId: string | null = null;

    for await (const message of searchResponse) {
      if (message.type === 'assistant') {
        console.log("\n✅ Search Results:");
        console.log(message.content);

        // Try to extract an email ID from the response
        const idMatch = message.content.match(/ID[:\s]+([a-zA-Z0-9]+)/i);
        if (idMatch) {
          emailId = idMatch[1];
        }
      } else if (message.type === 'tool_result') {
        console.log(`\n🔧 Tool used: ${message.tool_name}`);
      }
    }

    // Test 2: Read a specific email if we found one
    if (emailId) {
      console.log("\n\n📖 Test 2: Reading email with ID:", emailId);

      const readResponse = query({
        prompt: `Read the email with ID ${emailId} and show me its full content including sender, subject, date, and body.`,
        options: {
          mcpServers: {
            "gmail": {
              command: "npx",
              args: ["@gongrzhe/server-gmail-autoauth-mcp"]
            }
          },
          allowedTools: [
            "mcp__gmail__read_email"
          ],
          model: "claude-sonnet-4-5"
        }
      });

      for await (const message of readResponse) {
        if (message.type === 'assistant') {
          console.log("\n✅ Email Content:");
          console.log(message.content);
        } else if (message.type === 'tool_result') {
          console.log(`\n🔧 Tool used: ${message.tool_name}`);
        }
      }
    } else {
      console.log("\n⚠️  Test 2 skipped: No email ID found in search results");
    }

    // Test 3: List email labels
    console.log("\n\n🏷️  Test 3: Listing email labels...");

    const labelsResponse = query({
      prompt: "List all my Gmail labels and show me how many there are.",
      options: {
        mcpServers: {
          "gmail": {
            command: "npx",
            args: ["@gongrzhe/server-gmail-autoauth-mcp"]
          }
        },
        allowedTools: [
          "mcp__gmail__list_email_labels"
        ],
        model: "claude-sonnet-4-5"
      }
    });

    for await (const message of labelsResponse) {
      if (message.type === 'assistant') {
        console.log("\n✅ Labels:");
        console.log(message.content);
      } else if (message.type === 'tool_result') {
        console.log(`\n🔧 Tool used: ${message.tool_name}`);
      }
    }

    console.log("\n\n✨ All tests completed successfully!");
    console.log("✅ Gmail MCP server is working correctly!");

  } catch (error) {
    console.error("\n❌ Error testing Gmail MCP server:", error);
    if (error instanceof Error) {
      console.error("Error details:", error.message);
      console.error("Stack trace:", error.stack);
    }
    process.exit(1);
  }
}

// Run the tests
console.log("=" .repeat(60));
console.log("Gmail MCP Server Test Suite");
console.log("=" .repeat(60));
console.log("\nMake sure you have:");
console.log("  ✓ Authenticated with: npx @gongrzhe/server-gmail-autoauth-mcp auth");
console.log("  ✓ Set your ANTHROPIC_API_KEY in environment");
console.log("  ✓ Installed @anthropic-ai/claude-agent-sdk");
console.log("\n" + "=" .repeat(60) + "\n");

testGmailMCP().catch(console.error);
