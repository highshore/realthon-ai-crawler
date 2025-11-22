"use client";

import { useState } from "react";
import { 
  Play, 
  Code, 
  Terminal, 
  Loader2, 
  CheckCircle2, 
  AlertCircle,
  Globe,
  User,
  Cpu,
  Zap,
  ChevronRight
} from "lucide-react";
import axios from "axios";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// Utility for merging tailwind classes
function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

export default function Home() {
  const [url, setUrl] = useState("https://linkareer.com/list/intern?filterBy_activityTypeID=5&filterBy_categoryIDs=58&filterBy_jobTypes=INTERN&filterBy_regionIDs=2&filterBy_status=OPEN&orderBy_direction=DESC&orderBy_field=RECENT&page=1");
  
  // User profile now defaults to the raw text string
  const [userProfile, setUserProfile] = useState(`"Sookyum “Kyle” Kim is a Korea University junior majoring in Computer Science and Engineering (graduating 2027) with strong fundamentals in machine learning, data science, Python, and cloud technologies, backed by AWS Solutions Architect Associate and AI Practitioner certifications. He has hands-on product and engineering experience through building “1 Cup English,” a fully functional, paid web service he developed end to end using React, Next.js, Firebase, Google Cloud, and LLM fine-tuning, as well as “K Saju,” a hackathon-winning project using Supabase and PostgreSQL. Alongside his technical work, he brings over six years of professional interpretation experience at Sendbird, CJ Foods, and the ROK/US Combined Forces Command, supporting executive meetings, customer negotiations, and engineering discussions—giving him a rare combination of engineering ability, communication strength, and real-world product execution. He's NOT interested in ML Engineering. But he wants to grab every opportunity related to 전문연구요원."`);

  // Updated with the actual Lambda Function URL
  const [apiEndpoint, setApiEndpoint] = useState("https://65f7rivlixzixouwamk4kbuo2a0uphfv.lambda-url.ap-northeast-2.on.aws/");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "response">("preview");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setResponse(null);
    setActiveTab("response");

    try {
      let parsedProfile;
      try {
        parsedProfile = JSON.parse(userProfile);
      } catch (err) {
        parsedProfile = userProfile;
      }

      const payload = {
        url,
        user_profile: parsedProfile
      };

      if (!apiEndpoint) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        throw new Error("Please provide an API Endpoint to execute the request.");
      }

      const res = await axios.post("/api/crawl", {
        endpoint: apiEndpoint,
        ...payload
      });
      setResponse(res.data);
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || "An error occurred");
      if (err.response?.data?.details) {
        setResponse(err.response.data.details);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const getRequestPreview = () => {
    let parsedProfile;
    try {
      parsedProfile = JSON.parse(userProfile);
    } catch {
      parsedProfile = userProfile;
    }

    const payload = {
      url,
      user_profile: parsedProfile
    };

    return {
      method: "POST",
      url: apiEndpoint || "<YOUR_LAMBDA_URL>",
      headers: {
        "Content-Type": "application/json"
      },
      body: payload
    };
  };

  return (
    <div className="min-h-screen bg-[#fafafa] text-neutral-900 font-sans selection:bg-black selection:text-white">
      {/* Header */}
      <header className="bg-white border-b border-neutral-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-black text-white w-8 h-8 flex items-center justify-center rounded-lg font-bold shadow-sm">
              <Cpu className="w-5 h-5" />
            </div>
            <h1 className="font-semibold text-lg tracking-tight text-neutral-900">Crawler Agent</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-50 border border-green-200 text-green-700 text-xs font-medium">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              System Operational
            </div>
            <div className="text-xs font-medium text-neutral-500">v1.2.0</div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 md:py-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Configuration */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-white rounded-xl border border-neutral-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-neutral-100 bg-neutral-50/50 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-neutral-900 flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-neutral-500" />
                  Configuration
                </h2>
                <span className="text-[10px] uppercase tracking-wider font-bold text-neutral-400">Input Parameters</span>
              </div>
              
              <form onSubmit={handleSubmit} className="p-6 space-y-5">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-neutral-700 uppercase tracking-wide">API Endpoint</label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Zap className="h-4 w-4 text-neutral-400 group-focus-within:text-black transition-colors" />
                    </div>
                    <input
                      type="text"
                      value={apiEndpoint}
                      onChange={(e) => setApiEndpoint(e.target.value)}
                      placeholder="https://..."
                      className="block w-full pl-10 pr-3 py-2.5 bg-white border border-neutral-200 rounded-lg text-sm text-neutral-800 placeholder-neutral-400 focus:outline-none focus:border-black focus:ring-1 focus:ring-black transition-all shadow-sm"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-neutral-700 uppercase tracking-wide">Target URL</label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Globe className="h-4 w-4 text-neutral-400 group-focus-within:text-black transition-colors" />
                    </div>
                    <input
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      className="block w-full pl-10 pr-3 py-2.5 bg-white border border-neutral-200 rounded-lg text-sm text-neutral-800 focus:outline-none focus:border-black focus:ring-1 focus:ring-black transition-all shadow-sm"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-neutral-700 uppercase tracking-wide">User Profile</label>
                  <div className="relative group">
                    <div className="absolute top-3 left-3 pointer-events-none">
                      <User className="h-4 w-4 text-neutral-400 group-focus-within:text-black transition-colors" />
                    </div>
                    <textarea
                      value={userProfile}
                      onChange={(e) => setUserProfile(e.target.value)}
                      rows={10}
                      className="block w-full pl-10 pr-3 py-2.5 bg-white border border-neutral-200 rounded-lg text-sm font-mono text-neutral-700 leading-relaxed focus:outline-none focus:border-black focus:ring-1 focus:ring-black transition-all shadow-sm resize-none"
                    />
                  </div>
                  <p className="text-[10px] text-neutral-400 flex items-center justify-between px-1">
                    <span>Supports raw text or JSON format.</span>
                    <span>{userProfile.length} chars</span>
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full group bg-black hover:bg-neutral-800 text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all shadow-md hover:shadow-lg disabled:opacity-70 disabled:cursor-not-allowed active:scale-[0.99]"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-neutral-400" />
                        <span className="text-neutral-200">Processing Request...</span>
                      </>
                    ) : (
                      <>
                        <span className="text-sm">Start Crawling Job</span>
                        <ChevronRight className="w-4 h-4 text-neutral-400 group-hover:translate-x-0.5 transition-transform" />
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
            
            {/* Helpful Tips / Status Card (Optional decorative element) */}
            <div className="bg-neutral-100 rounded-xl p-5 border border-neutral-200">
              <h3 className="text-xs font-bold uppercase text-neutral-500 mb-3">Capabilities</h3>
              <div className="space-y-2">
                {['Multi-source routing', 'OpenAI profile alignment', 'Headless browser support', 'Firecrawl fallback'].map((item, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-neutral-600">
                    <div className="w-1 h-1 rounded-full bg-neutral-400" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Output */}
          <div className="lg:col-span-7 space-y-6">
            <div className="bg-white rounded-xl border border-neutral-200 shadow-sm overflow-hidden h-full min-h-[650px] flex flex-col">
              <div className="border-b border-neutral-100 flex bg-neutral-50/50">
                <button
                  onClick={() => setActiveTab("preview")}
                  className={cn(
                    "px-5 py-3 text-xs font-semibold flex items-center gap-2 transition-colors border-b-2 outline-none",
                    activeTab === "preview" 
                      ? "border-black text-black bg-white" 
                      : "border-transparent text-neutral-500 hover:text-neutral-700 hover:bg-white/50"
                  )}
                >
                  <Code className="w-3.5 h-3.5" />
                  Request Preview
                </button>
                <button
                  onClick={() => setActiveTab("response")}
                  className={cn(
                    "px-5 py-3 text-xs font-semibold flex items-center gap-2 transition-colors border-b-2 outline-none",
                    activeTab === "response" 
                      ? "border-black text-black bg-white" 
                      : "border-transparent text-neutral-500 hover:text-neutral-700 hover:bg-white/50"
                  )}
                >
                  {error ? <AlertCircle className="w-3.5 h-3.5 text-red-500" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  Response Payload
                </button>
              </div>

              <div className="flex-1 bg-neutral-50 relative overflow-hidden">
                {activeTab === "preview" && (
                  <div className="absolute inset-0 overflow-auto p-0">
                    <div className="p-6 space-y-6">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="text-xs font-bold text-neutral-500 uppercase tracking-wide">CURL Command</div>
                          <div className="text-[10px] text-neutral-400 font-mono">bash</div>
                        </div>
                        <div className="bg-white rounded-lg border border-neutral-200 shadow-sm overflow-hidden group">
                          <div className="flex gap-1.5 p-3 border-b border-neutral-50 bg-neutral-50/30">
                            <div className="w-2.5 h-2.5 rounded-full bg-neutral-200" />
                            <div className="w-2.5 h-2.5 rounded-full bg-neutral-200" />
                            <div className="w-2.5 h-2.5 rounded-full bg-neutral-200" />
                          </div>
                          <pre className="p-4 text-xs font-mono text-neutral-700 whitespace-pre-wrap leading-relaxed overflow-x-auto">
                            {`curl -X POST "${getRequestPreview().url}" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(getRequestPreview().body, null, 2)}'`}
                          </pre>
                        </div>
                      </div>
                      
                      <div>
                        <div className="text-xs font-bold text-neutral-500 uppercase tracking-wide mb-2">Structured Payload</div>
                        <div className="bg-white rounded-lg border border-neutral-200 shadow-sm overflow-hidden">
                           <pre className="p-4 text-xs font-mono text-blue-600 whitespace-pre-wrap leading-relaxed overflow-x-auto">
                            {JSON.stringify(getRequestPreview().body, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "response" && (
                  <div className="absolute inset-0 overflow-auto">
                    {isLoading ? (
                      <div className="h-full flex flex-col items-center justify-center gap-4 p-8">
                        <div className="relative">
                          <div className="w-12 h-12 rounded-full border-2 border-neutral-100"></div>
                          <div className="absolute top-0 left-0 w-12 h-12 rounded-full border-2 border-black border-t-transparent animate-spin"></div>
                        </div>
                        <div className="text-center space-y-1">
                          <p className="text-sm font-medium text-neutral-900">Running Crawler...</p>
                          <p className="text-xs text-neutral-500">This may take up to 2 minutes depending on the target.</p>
                        </div>
                      </div>
                    ) : error ? (
                      <div className="h-full p-6">
                        <div className="bg-red-50 rounded-xl border border-red-100 p-6 shadow-sm">
                          <div className="flex items-start gap-4">
                            <div className="bg-red-100 p-2 rounded-lg">
                               <AlertCircle className="w-5 h-5 text-red-600" />
                            </div>
                            <div className="space-y-1">
                              <h3 className="text-sm font-bold text-red-900">Execution Failed</h3>
                              <p className="text-xs text-red-700 leading-relaxed">{error}</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : response ? (
                      <div className="min-h-full">
                         <pre className="p-6 text-xs font-mono text-neutral-800 whitespace-pre-wrap leading-relaxed">
                          {JSON.stringify(response, null, 2)}
                        </pre>
                      </div>
                    ) : (
                      <div className="h-full flex flex-col items-center justify-center text-neutral-400 gap-3">
                        <Play className="w-12 h-12 text-neutral-200" />
                        <p className="text-sm font-medium">Ready to execute</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
