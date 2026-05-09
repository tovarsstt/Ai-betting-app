import Anthropic from '@anthropic-ai/sdk';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '../../.env'), override: true });

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const DEEPSEEK_KEY = process.env.DEEPSEEK_API_KEY || "";
const GEMINI_KEY = process.env.GEMINI_API_KEY || "";

export type ModelProvider = 'anthropic' | 'deepseek' | 'gemini';

export class ModelRouter {
  private static instance: ModelRouter;
  
  private constructor() {}

  public static getInstance(): ModelRouter {
    if (!ModelRouter.instance) {
      ModelRouter.instance = new ModelRouter();
    }
    return ModelRouter.instance;
  }

  /**
   * Primary prompt execution with automated failover
   */
  async ask(prompt: string, options: { model?: string; provider?: ModelProvider } = {}): Promise<string> {
    const { provider = 'anthropic', model = 'claude-3-5-sonnet-20241022' } = options;

    try {
      if (provider === 'anthropic') {
        return await this.callAnthropic(prompt, model);
      } else if (provider === 'deepseek') {
        return await this.callDeepSeek(prompt);
      } else {
        return await this.callGemini(prompt);
      }
    } catch (err: any) {
      console.warn(`[ModelRouter] ${provider} failed. Attempting failover...`);
      
      // Automatic Fallback Sequence: Anthropic -> DeepSeek -> Gemini
      if (provider === 'anthropic' && DEEPSEEK_KEY) {
        return await this.callDeepSeek(prompt);
      } else if (provider === 'deepseek' && GEMINI_KEY) {
        return await this.callGemini(prompt);
      }
      
      throw err;
    }
  }

  private async callAnthropic(prompt: string, model: string): Promise<string> {
    const msg = await anthropic.messages.create({
      model,
      max_tokens: 4096,
      messages: [{ role: "user", content: prompt }],
    });
    const text = msg.content[0].type === "text" ? msg.content[0].text : "";
    return text.replace(/```json|```/g, "").trim();
  }

  private async callDeepSeek(prompt: string): Promise<string> {
    if (!DEEPSEEK_KEY) throw new Error("DeepSeek key missing");
    
    const res = await fetch("https://api.deepseek.com/v1/chat/completions", {
      method: "POST",
      headers: { 
        "Content-Type": "application/json", 
        "Authorization": `Bearer ${DEEPSEEK_KEY}` 
      },
      body: JSON.stringify({ 
        model: "deepseek-chat", 
        messages: [{ role: "user", content: prompt }], 
        max_tokens: 4096 
      }),
    });
    
    const data = await res.json() as any;
    return (data.choices?.[0]?.message?.content || "").replace(/```json|```/g, "").trim();
  }

  private async callGemini(prompt: string): Promise<string> {
    if (!GEMINI_KEY) throw new Error("Gemini key missing");
    
    // Using standard fetch for Google AI API
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=${GEMINI_KEY}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: 4096 }
      }),
    });
    
    const data = await res.json() as any;
    return (data.candidates?.[0]?.content?.parts?.[0]?.text || "").replace(/```json|```/g, "").trim();
  }
}

export const router = ModelRouter.getInstance();
