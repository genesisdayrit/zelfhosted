"use client";

import { useState, useRef, useEffect } from "react";
import { ZELF_LOGO } from "./ascii-art-logo";

interface YouTubeEmbed {
  videoId: string;
  title: string;
  channel: string;
}

interface SpotifyEmbed {
  contentType: "track" | "artist" | "album" | "playlist";
  id: string;
  name: string;
  artist: string;
}

interface TraceEvent {
  id: string;
  type: "node" | "tool";
  name: string;
  status: "running" | "complete";
  timestamp: number;
  // Tool-specific fields
  args?: Record<string, unknown>;
  result?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  youtubeEmbeds?: YouTubeEmbed[];
  spotifyEmbeds?: SpotifyEmbed[];
  traceEvents?: TraceEvent[];
}

interface UserLocation {
  lat: number;
  lon: number;
}

// Tool icons mapping
const TOOL_ICONS: Record<string, string> = {
  get_weather: "🌤️",
  get_polymarket_opportunities: "📈",
  get_arxiv_articles: "📚",
  get_latest_photos: "📷",
  search_youtube_song: "🎵",
  search_spotify: "🎧",
  exa_search: "🔍",
  exa_find_similar: "🔗",
  exa_answer: "💡",
  default: "⚡",
};

// Terminal-styled markdown renderer
function TerminalMarkdown({ content }: { content: string }) {
  // Parse markdown and render with terminal styling
  const renderContent = (text: string) => {
    const elements: React.ReactNode[] = [];
    let key = 0;

    // Split by lines first to handle line breaks
    const lines = text.split("\n");

    lines.forEach((line, lineIndex) => {
      if (lineIndex > 0) {
        elements.push(<br key={`br-${key++}`} />);
      }

      // Process each line for inline markdown
      let remaining = line;
      const lineElements: React.ReactNode[] = [];

      while (remaining.length > 0) {
        // Check for YouTube embed: {{youtube:VIDEO_ID}}
        const youtubeMatch = remaining.match(/^\{\{youtube:([a-zA-Z0-9_-]+)\}\}/);
        if (youtubeMatch) {
          const videoId = youtubeMatch[1];
          lineElements.push(
            <div key={key++} className="my-3">
              <iframe
                width="100%"
                height="315"
                src={`https://www.youtube.com/embed/${videoId}`}
                title="YouTube video"
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="rounded-lg border border-[#8b5cf6]/30 shadow-lg max-w-md"
              />
            </div>
          );
          remaining = remaining.slice(youtubeMatch[0].length);
          continue;
        }

        // Check for image: ![alt](url)
        const imageMatch = remaining.match(/^!\[([^\]]*)\]\(([^)]+)\)/);
        if (imageMatch) {
          lineElements.push(
            <img
              key={key++}
              src={imageMatch[2]}
              alt={imageMatch[1]}
              className="my-2 max-w-full rounded-lg border border-[#8b5cf6]/30 shadow-lg"
            />
          );
          remaining = remaining.slice(imageMatch[0].length);
          continue;
        }

        // Check for bold with link: **[text](url)**
        const boldLinkMatch = remaining.match(
          /^\*\*\[([^\]]+)\]\(([^)]+)\)\*\*/
        );
        if (boldLinkMatch) {
          lineElements.push(
            <a
              key={key++}
              href={boldLinkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#8b5cf6] hover:text-[#a78bfa] underline underline-offset-2"
            >
              {boldLinkMatch[1]}
            </a>
          );
          remaining = remaining.slice(boldLinkMatch[0].length);
          continue;
        }

        // Check for link: [text](url)
        const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/);
        if (linkMatch) {
          lineElements.push(
            <a
              key={key++}
              href={linkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#06b6d4] hover:text-[#22d3ee] underline underline-offset-2"
            >
              {linkMatch[1]}
            </a>
          );
          remaining = remaining.slice(linkMatch[0].length);
          continue;
        }

        // Check for bold: **text**
        const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/);
        if (boldMatch) {
          lineElements.push(
            <span key={key++} className="text-[#d4a574] font-semibold">
              {boldMatch[1]}
            </span>
          );
          remaining = remaining.slice(boldMatch[0].length);
          continue;
        }

        // Check for italic: _text_ or *text*
        const italicMatch = remaining.match(/^[_*]([^_*]+)[_*]/);
        if (italicMatch) {
          lineElements.push(
            <span key={key++} className="text-[#8b7355] italic">
              {italicMatch[1]}
            </span>
          );
          remaining = remaining.slice(italicMatch[0].length);
          continue;
        }

        // Check for inline code: `code`
        const codeMatch = remaining.match(/^`([^`]+)`/);
        if (codeMatch) {
          lineElements.push(
            <code
              key={key++}
              className="bg-[#2a2520] text-[#22c55e] px-1.5 py-0.5 rounded text-sm"
            >
              {codeMatch[1]}
            </code>
          );
          remaining = remaining.slice(codeMatch[0].length);
          continue;
        }

        // No match - consume one character
        const nextSpecial = remaining.search(/[!\[*_`]/);
        if (nextSpecial === -1) {
          lineElements.push(remaining);
          remaining = "";
        } else if (nextSpecial === 0) {
          // Special char that didn't match a pattern - treat as text
          lineElements.push(remaining[0]);
          remaining = remaining.slice(1);
        } else {
          lineElements.push(remaining.slice(0, nextSpecial));
          remaining = remaining.slice(nextSpecial);
        }
      }

      elements.push(...lineElements);
    });

    return elements;
  };

  return <>{renderContent(content)}</>;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [youtubeEmbeds, setYoutubeEmbeds] = useState<YouTubeEmbed[]>([]);
  const [spotifyEmbeds, setSpotifyEmbeds] = useState<SpotifyEmbed[]>([]);
  const [expandedTraces, setExpandedTraces] = useState<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  const traceEventsRef = useRef<TraceEvent[]>([]);
  const youtubeEmbedsRef = useRef<YouTubeEmbed[]>([]);
  const spotifyEmbedsRef = useRef<SpotifyEmbed[]>([]);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // Request browser geolocation on mount (optional - user can deny)
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setUserLocation({
            lat: position.coords.latitude,
            lon: position.coords.longitude,
          });
        },
        () => {
          // User denied or error - that's fine, location is optional
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
      );
    }
  }, []);

  // Keep refs in sync with state for closure access
  useEffect(() => {
    traceEventsRef.current = traceEvents;
  }, [traceEvents]);

  useEffect(() => {
    youtubeEmbedsRef.current = youtubeEmbeds;
  }, [youtubeEmbeds]);

  useEffect(() => {
    spotifyEmbedsRef.current = spotifyEmbeds;
  }, [spotifyEmbeds]);

  const toggleTraceExpansion = (index: number) => {
    setExpandedTraces((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || streamingRef.current) return;

    if (streamingRef.current) return;
    streamingRef.current = true;

    const userMessage = input.trim();
    setInput("");

    // Finalize embeds and trace events on the last assistant message before adding new messages
    setMessages((prev) => {
      const updated = [...prev];
      const lastAssistantIdx = updated.map(m => m.role).lastIndexOf("assistant");
      if (lastAssistantIdx >= 0) {
        updated[lastAssistantIdx] = {
          ...updated[lastAssistantIdx],
          youtubeEmbeds: youtubeEmbeds.length > 0 ? youtubeEmbeds : updated[lastAssistantIdx].youtubeEmbeds,
          spotifyEmbeds: spotifyEmbeds.length > 0 ? spotifyEmbeds : updated[lastAssistantIdx].spotifyEmbeds,
          traceEvents: traceEvents.length > 0 ? traceEvents : updated[lastAssistantIdx].traceEvents,
        };
      }
      return [...updated, { role: "user", content: userMessage }];
    });

    setIsStreaming(true);
    setTraceEvents([]);
    setYoutubeEmbeds([]);
    setSpotifyEmbeds([]);

    setMessages((prev) => [...prev, { role: "assistant", content: "", youtubeEmbeds: [], spotifyEmbeds: [], traceEvents: [] }]);

    abortControllerRef.current = new AbortController();

    let accumulatedContent = "";

    // Build messages array including all previous messages plus the new user message
    const allMessages = [...messages, { role: "user" as const, content: userMessage }];

    try {
      const response = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          messages: allMessages,  // Send full conversation history
          location: userLocation,  // Optional - null if user denied permission
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error("Failed to fetch");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error("No reader available");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "node_start") {
                const newEvent: TraceEvent = {
                  id: `node-${data.node}-${Date.now()}`,
                  type: "node",
                  name: data.node,
                  status: "running",
                  timestamp: Date.now(),
                };
                setTraceEvents((prev) => [...prev, newEvent]);
              } else if (data.type === "tool_call") {
                const newEvent: TraceEvent = {
                  id: `tool-${data.tool}-${Date.now()}`,
                  type: "tool",
                  name: data.tool,
                  status: "running",
                  timestamp: Date.now(),
                  args: data.args,
                };
                setTraceEvents((prev) => [...prev, newEvent]);
              } else if (data.type === "tool_result") {
                setTraceEvents((prev) =>
                  prev.map((event) =>
                    event.type === "tool" &&
                    event.name === data.tool &&
                    event.status === "running"
                      ? { ...event, status: "complete" as const, result: data.result }
                      : event
                  )
                );
              } else if (data.type === "token") {
                accumulatedContent += data.content;
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMessage = updated[updated.length - 1];
                  if (lastMessage?.role === "assistant") {
                    lastMessage.content = accumulatedContent;
                  }
                  return updated;
                });
              } else if (data.type === "node_complete") {
                setTraceEvents((prev) =>
                  prev.map((event) =>
                    event.type === "node" &&
                    event.name === data.node &&
                    event.status === "running"
                      ? { ...event, status: "complete" as const }
                      : event
                  )
                );
              } else if (data.type === "youtube_embed") {
                const newEmbed = {
                  videoId: data.video_id,
                  title: data.title,
                  channel: data.channel || "",
                };
                setYoutubeEmbeds((prev) => [...prev, newEmbed]);
              } else if (data.type === "spotify_embed") {
                const newEmbed = {
                  contentType: data.content_type as SpotifyEmbed["contentType"],
                  id: data.id,
                  name: data.name,
                  artist: data.artist || "",
                };
                setSpotifyEmbeds((prev) => [...prev, newEmbed]);
              } else if (data.type === "done") {
                // Finalize trace events and embeds on the message
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMessage = updated[updated.length - 1];
                  if (lastMessage?.role === "assistant") {
                    lastMessage.traceEvents = [...traceEventsRef.current];
                    lastMessage.youtubeEmbeds = [...youtubeEmbedsRef.current];
                    lastMessage.spotifyEmbeds = [...spotifyEmbedsRef.current];
                  }
                  return updated;
                });
                setIsStreaming(false);
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        return;
      }
      console.error("Error:", error);
      setMessages((prev) => {
        const updated = [...prev];
        const lastMessage = updated[updated.length - 1];
        if (lastMessage?.role === "assistant") {
          lastMessage.content = "ERROR: Connection failed. Try again.";
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
      streamingRef.current = false;
    }
  };

  const formatToolArgs = (args: Record<string, unknown>) => {
    return Object.entries(args)
      .map(([key, value]) => `${key}: "${value}"`)
      .join(", ");
  };

  return (
    <div className="relative flex min-h-screen flex-col bg-[#1a1612] font-mono">
      {/* Scanline overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-50"
        style={{
          background:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.1) 2px, rgba(0,0,0,0.1) 4px)",
        }}
      />

      {/* Header */}
      <header className="border-b-2 border-[#8b5cf6]/30 bg-[#1a1612] px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <div className="flex gap-1.5">
            <button
              onClick={() => {
                if (isStreaming) {
                  abortControllerRef.current?.abort();
                }
                setMessages([]);
                setTraceEvents([]);
                setYoutubeEmbeds([]);
                setSpotifyEmbeds([]);
                setInput("");
                setIsStreaming(false);
                streamingRef.current = false;
              }}
              className="h-3 w-3 rounded-full bg-[#ef4444] hover:bg-[#f87171] transition-colors cursor-pointer"
              title="Clear chat"
            />
            <span className="h-3 w-3 rounded-full bg-[#d4a574]" />
            <span className="h-3 w-3 rounded-full bg-[#22c55e]" />
          </div>
          <span className="text-sm text-[#d4a574]">
            zelfhosted@terminal:~$
          </span>
          <span className="animate-pulse text-[#22c55e]">▋</span>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {messages.length === 0 ? (
            <div className="flex h-[60vh] flex-col items-center justify-center text-center">
              <pre className="mb-6 text-[#8b5cf6] text-xs leading-tight">
                {ZELF_LOGO}
              </pre>
              <p className="text-[#d4a574]">
                {">"} SYSTEM READY. ENTER QUERY TO BEGIN_
              </p>
              <p className="mt-2 text-xs text-[#8b7355]">
                [LangGraph Neural Interface v0.1.0]
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div key={index} className="space-y-2">
                  {/* Execution trace - collapsible after completion */}
                  {(() => {
                    const isCurrentlyStreaming = isStreaming && index === messages.length - 1;
                    // During streaming: use global traceEvents; after: use message.traceEvents
                    const currentTraces = isCurrentlyStreaming ? traceEvents : message.traceEvents;
                    const toolCount = currentTraces?.filter((e) => e.type === "tool").length || 0;
                    const isExpanded = expandedTraces.has(index) || isCurrentlyStreaming;

                    if (message.role !== "assistant" || !currentTraces || currentTraces.length === 0) {
                      return null;
                    }

                    return (
                      <div className="space-y-2 border-l-2 border-[#8b5cf6]/50 pl-3">
                        <span className="text-xs text-[#8b7355]">
                          [TRACE] {isExpanded ? "▼" : "▶"} {toolCount} tool{toolCount !== 1 ? "s" : ""}
                        </span>

                        {/* Compact trace flow - always visible */}
                        <div className="flex flex-wrap items-center gap-1 text-xs">
                          {currentTraces.map((event, i) => (
                            <div
                              key={event.id}
                              className="flex items-center"
                            >
                              {i > 0 && (
                                <span className="mx-1 text-[#8b7355]">→</span>
                              )}
                              {event.type === "node" ? (
                                <span
                                  className={`flex items-center gap-1 rounded border px-2 py-0.5 ${
                                    event.status === "running"
                                      ? "border-[#d4a574] bg-[#d4a574]/10 text-[#d4a574]"
                                      : "border-[#22c55e] bg-[#22c55e]/10 text-[#22c55e]"
                                  }`}
                                >
                                  {event.status === "running" ? (
                                    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#d4a574]" />
                                  ) : (
                                    <span>✓</span>
                                  )}
                                  {event.name}
                                </span>
                              ) : (
                                <span
                                  className={`flex items-center gap-1 rounded border px-2 py-0.5 ${
                                    event.status === "running"
                                      ? "border-[#f59e0b] bg-[#f59e0b]/10 text-[#f59e0b]"
                                      : "border-[#06b6d4] bg-[#06b6d4]/10 text-[#06b6d4]"
                                  }`}
                                >
                                  <span>{TOOL_ICONS[event.name] || TOOL_ICONS.default}</span>
                                  {event.name}
                                  {event.status === "running" ? (
                                    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#f59e0b]" />
                                  ) : (
                                    <span>✓</span>
                                  )}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Tool details panel - collapsible */}
                        {currentTraces.some((e) => e.type === "tool") && (
                          <button
                            onClick={() => toggleTraceExpansion(index)}
                            className="text-xs text-[#8b7355] hover:text-[#d4a574] cursor-pointer"
                          >
                            {isExpanded ? "Hide" : "Show"} details
                          </button>
                        )}
                        {isExpanded && currentTraces.some((e) => e.type === "tool") && (
                              <div className="mt-2 space-y-1.5">
                                {currentTraces
                                  .filter((e) => e.type === "tool")
                                  .map((tool) => (
                                    <div
                                      key={tool.id}
                                      className="rounded border border-[#06b6d4]/30 bg-[#06b6d4]/5 p-2 text-xs"
                                    >
                                      <div className="flex items-center gap-2">
                                        <span className="text-lg">
                                          {TOOL_ICONS[tool.name] || TOOL_ICONS.default}
                                        </span>
                                        <span className="font-semibold text-[#06b6d4]">
                                          {tool.name}
                                        </span>
                                        {tool.status === "running" ? (
                                          <span className="flex items-center gap-1 text-[#f59e0b]">
                                            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[#f59e0b]" />
                                            executing...
                                          </span>
                                        ) : (
                                          <span className="text-[#22c55e]">✓ complete</span>
                                        )}
                                      </div>
                                      {tool.args && (
                                        <div className="mt-1 text-[#8b7355]">
                                          <span className="text-[#a78bfa]">args:</span>{" "}
                                          <span className="text-[#e8dcc4]">
                                            {formatToolArgs(tool.args)}
                                          </span>
                                        </div>
                                      )}
                                      {tool.result && (
                                        <div className="mt-1 text-[#8b7355]">
                                          <span className="text-[#a78bfa]">result:</span>{" "}
                                          <span className="text-[#22c55e]">
                                            &quot;{tool.result}&quot;
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                  ))}
                              </div>
                            )}
                      </div>
                    );
                  })()}

                  {/* Message */}
                  <div
                    className={`border-l-2 pl-3 ${
                      message.role === "user"
                        ? "border-[#8b5cf6]"
                        : "border-[#22c55e]"
                    }`}
                  >
                    <div className="mb-1 flex items-center gap-2 text-xs">
                      <span
                        className={
                          message.role === "user"
                            ? "text-[#8b5cf6]"
                            : "text-[#22c55e]"
                        }
                      >
                        {message.role === "user" ? "USER" : "SYSTEM"}
                      </span>
                      <span className="text-[#8b7355]">
                        {new Date().toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="text-[#e8dcc4] leading-relaxed">
                      <TerminalMarkdown content={message.content} />
                      {message.role === "assistant" &&
                        isStreaming &&
                        index === messages.length - 1 && (
                          <span className="ml-0.5 inline-block animate-pulse text-[#22c55e]">
                            ▋
                          </span>
                        )}
                    </div>

                    {/* YouTube embeds - render below assistant message */}
                    {(() => {
                      const isCurrentlyStreaming = isStreaming && index === messages.length - 1;
                      const currentYoutubeEmbeds = isCurrentlyStreaming ? youtubeEmbeds : message.youtubeEmbeds;
                      if (message.role !== "assistant" || !currentYoutubeEmbeds || currentYoutubeEmbeds.length === 0) return null;
                      return (
                        <div className="mt-4 space-y-4">
                          {currentYoutubeEmbeds.map((embed, embedIndex) => (
                            <div key={embedIndex} className="space-y-1">
                              <div className="text-xs text-[#8b7355]">
                                🎵 {embed.title}
                                {embed.channel && (
                                  <span className="text-[#6b5545]"> • {embed.channel}</span>
                                )}
                              </div>
                              <iframe
                                width="100%"
                                height="315"
                                src={`https://www.youtube.com/embed/${embed.videoId}`}
                                title={embed.title}
                                frameBorder="0"
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                allowFullScreen
                                className="rounded-lg border border-[#8b5cf6]/30 shadow-lg max-w-md"
                              />
                            </div>
                          ))}
                        </div>
                      );
                    })()}

                    {/* Spotify embeds - render below assistant message */}
                    {(() => {
                      const isCurrentlyStreaming = isStreaming && index === messages.length - 1;
                      const currentSpotifyEmbeds = isCurrentlyStreaming ? spotifyEmbeds : message.spotifyEmbeds;
                      if (message.role !== "assistant" || !currentSpotifyEmbeds || currentSpotifyEmbeds.length === 0) return null;
                      return (
                        <div className="mt-4 space-y-4">
                          {currentSpotifyEmbeds.map((embed, embedIndex) => (
                            <div key={embedIndex} className="space-y-1">
                              <div className="text-xs text-[#8b7355]">
                                🎧 {embed.name}
                                {embed.artist && (
                                  <span className="text-[#6b5545]"> • {embed.artist}</span>
                                )}
                              </div>
                              <iframe
                                src={`https://open.spotify.com/embed/${embed.contentType}/${embed.id}?utm_source=generator&theme=0`}
                                width="100%"
                                height={embed.contentType === "track" ? 152 : 352}
                                frameBorder="0"
                                allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                                loading="lazy"
                                className="rounded-lg border border-[#8b5cf6]/30 shadow-lg max-w-md"
                              />
                            </div>
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="border-t-2 border-[#8b5cf6]/30 bg-[#1a1612] p-4">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex items-center gap-2 rounded border-2 border-[#8b5cf6]/50 bg-[#0f0d0a] px-3 py-2 focus-within:border-[#8b5cf6] focus-within:shadow-[0_0_10px_rgba(139,92,246,0.3)]">
            <span className="text-[#22c55e]">{">"}</span>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Enter command..."
              disabled={isStreaming}
              className="flex-1 bg-transparent text-[#e8dcc4] placeholder-[#8b7355] outline-none disabled:opacity-50"
            />
            {isStreaming ? (
              <span className="flex items-center gap-1 text-xs text-[#d4a574]">
                <span className="inline-block h-2 w-2 animate-spin rounded-full border border-[#d4a574] border-t-transparent" />
                PROCESSING
              </span>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="text-xs text-[#8b5cf6] transition-colors hover:text-[#a78bfa] disabled:opacity-30"
              >
                [ENTER]
              </button>
            )}
          </div>
          <p className="mt-2 text-center text-xs text-[#8b7355]">
            Press ENTER to execute • ESC to cancel
          </p>
        </form>
      </div>
    </div>
  );
}
