import OpenAI from "openai";

// OpenRouter is OpenAI-compatible — use openai SDK with base_url override
const client = new OpenAI({
  apiKey: "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",
  baseURL: "https://openrouter.ai/api/v1",
  defaultHeaders: {
    "HTTP-Referer": "https://github.com/george-job-agent",
    "X-Title": "George Job Agent"
  }
});

console.log("Testing OpenRouter → nvidia/nemotron-3-super:free ...\n");

const stream = await client.chat.completions.create({
  model: "nvidia/nemotron-3-super-120b-a12b:free",
  messages: [
    {
      role: "user",
      content: "How many r's are in the word 'strawberry'? Count carefully."
    }
  ],
  stream: true,
  stream_options: { include_usage: true }
});

let response = "";
for await (const chunk of stream) {
  const content = chunk.choices[0]?.delta?.content;
  if (content) {
    response += content;
    process.stdout.write(content);
  }
  if (chunk.usage) {
    console.log("\n\n--- Usage ---");
    console.log("Prompt tokens:     ", chunk.usage.prompt_tokens);
    console.log("Completion tokens: ", chunk.usage.completion_tokens);
    console.log("Total tokens:      ", chunk.usage.total_tokens);
  }
}

console.log("\n\n✅ OpenRouter connection works!");
