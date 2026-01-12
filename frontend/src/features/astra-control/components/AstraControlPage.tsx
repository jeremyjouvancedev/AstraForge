import React, { useState, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAstraControl } from '../hooks/useAstraControl';
import { LLMSelectionFields, LLMProvider, ReasoningEffort } from '@/features/chat/components/llm-selection-fields';
import { type AstraControlSession, type PlanStep } from '../types';
import { cn } from '@/lib/utils';
import { 
  Plus, 
  Terminal, 
  CheckCircle2, 
  AlertCircle, 
  Play, 
  History, 
  Settings2,
  Clock,
  ListTodo,
  Circle
} from 'lucide-react';

function summarizeSessions(sessions: AstraControlSession[]) {
  let running = 0;
  let completed = 0;
  let failed = 0;
  sessions.forEach((s) => {
    if (s.status === 'running') running += 1;
    if (s.status === 'completed') completed += 1;
    if (s.status === 'failed') failed += 1;
  });
  return { total: sessions.length, running, completed, failed };
}

export function AstraControlPage() {
  const [view, setView] = useState<'setup' | 'live'>('setup');
  const [goal, setGoal] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AstraControlSession[]>([]);
  const [llmProvider, setLlmProvider] = useState<LLMProvider>('ollama');
  const [llmModel, setLlmModel] = useState('devstral-small-2:24b');
  const [reasoningCheck, setReasoningCheck] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('high');

  const [planTab, setPlanTab] = useState<'checklist' | 'markdown'>('checklist');

  const { events, status, startSession, resumeSession, fetchSessions } = useAstraControl(sessionId);

  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, [fetchSessions]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, sessionId]);

  const summary = useMemo(() => summarizeSessions(sessions), [sessions]);

  const activeSession = useMemo(() => {
    return sessions.find(s => s.id === sessionId) || null;
  }, [sessions, sessionId]);

  const { planSteps, rawPlan } = useMemo(() => {
    const plannerEvents = events.filter(e => e.type === 'planner');
    if (plannerEvents.length === 0) return { planSteps: [], rawPlan: '' };
    const latestPlanner = plannerEvents[plannerEvents.length - 1];
    const payload = latestPlanner.payload;
    return {
      planSteps: (payload.plan_steps || []) as PlanStep[],
      rawPlan: payload.plan || ''
    };
  }, [events]);

  const handleStart = async () => {
    if (!goal) return;
    try {
      const session = await startSession(
        goal, 
        llmModel, 
        llmProvider, 
        reasoningCheck, 
        reasoningEffort
      );
      // Immediately add the new session to the list so it's available for find()
      setSessions(prev => [session, ...prev]);
      setSessionId(session.id);
      setView('live');
    } catch (err) {
      console.error("Failed to start agent session:", err);
    }
  };

  const handleResume = async () => {
    try {
      await resumeSession();
    } catch (err) {
      console.error("Failed to resume session:", err);
    }
  };

  const handleSelectSession = (id: string) => {
    setSessionId(id);
    setView('live');
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-[clamp(72rem,85vw,120rem)] space-y-8 px-4 py-8 text-zinc-100 sm:px-6 lg:px-10">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-2">
           <div className="flex items-center gap-2 text-blue-400 font-semibold uppercase tracking-[0.2em] text-[10px]">
             <Terminal className="h-3 w-3" />
             Astra Control
           </div>
           <h1 className="text-4xl font-bold text-white tracking-tight">System Control</h1>
           <p className="text-zinc-400 max-w-xl text-sm leading-relaxed">
             Execute complex system tasks across your Ubuntu environments with autonomous terminal agents.
           </p>
        </div>

        <div className="flex items-center gap-4 bg-black/40 border border-white/10 rounded-2xl p-1 shadow-xl">
           <Button 
            variant={view === "setup" ? "secondary" : "ghost"} 
            onClick={() => setView("setup")}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             <Plus className="h-4 w-4 mr-2" />
             New Task
           </Button>
           <Button 
            variant={view === "live" ? "secondary" : "ghost"} 
            onClick={() => setView("live")}
            disabled={!sessionId}
            className="rounded-xl h-10 px-6 font-medium transition-all"
           >
             Live Stream
           </Button>
        </div>
      </header>

      {view === 'setup' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr,320px] gap-8 items-start animate-in fade-in slide-in-from-bottom-4 duration-500">
          <Card className="border-white/5 bg-zinc-900/50 backdrop-blur-md rounded-3xl overflow-hidden shadow-2xl">
            <CardHeader className="border-b border-white/5 bg-white/[0.02] p-6">
              <CardTitle className="text-xl flex items-center gap-2">
                <Play className="h-5 w-5 text-blue-500 fill-blue-500/20" />
                Initialize Environment Agent
              </CardTitle>
            </CardHeader>
            <CardContent className="p-8 space-y-8">
              <div className="space-y-4">
                <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Execution Goal</label>
                <div className="flex space-x-3">
                  <Input 
                    value={goal} 
                    onChange={(e) => setGoal(e.target.value)} 
                    placeholder="e.g. Install nodejs and create a hello world app"
                    className="h-12 bg-black/40 border-white/10 rounded-xl focus:ring-blue-500/50 transition-all"
                  />
                  <Button 
                    onClick={handleStart} 
                    disabled={!goal}
                    className="h-12 px-8 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold shadow-lg shadow-blue-900/20 transition-all"
                  >
                    Launch
                  </Button>
                </div>
              </div>
              
              <div className="pt-6 border-t border-white/5">
                <div className="flex items-center gap-2 mb-6">
                  <Settings2 className="h-4 w-4 text-zinc-500" />
                  <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                    Engine Configuration
                  </label>
                </div>
                <div className="p-6 bg-black/20 rounded-2xl border border-white/5">
                  <LLMSelectionFields
                    provider={llmProvider}
                    onProviderChange={(val) => setLlmProvider(val as LLMProvider)}
                    model={llmModel}
                    onModelChange={setLlmModel}
                    reasoningCheck={reasoningCheck}
                    onReasoningCheckChange={setReasoningCheck}
                    reasoningEffort={reasoningEffort}
                    onReasoningEffortChange={setReasoningEffort}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md shadow-xl">
               <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                 <Terminal className="h-4 w-4" />
                 Fleet Status
               </h3>
               <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <Clock className="h-3.5 w-3.5 text-blue-400" />
                       Active
                     </div>
                     <span className="text-lg font-bold text-white">{summary.running}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                       Success
                     </div>
                     <span className="text-lg font-bold text-emerald-400">{summary.completed}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-2xl bg-white/5 border border-white/5">
                     <div className="flex items-center gap-2 text-xs text-zinc-400">
                       <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                       Failed
                     </div>
                     <span className="text-lg font-bold text-red-400">{summary.failed}</span>
                  </div>
               </div>
            </div>

            {sessions.length > 0 && (
              <div className="rounded-3xl border border-white/10 bg-black/30 p-6 space-y-4 backdrop-blur-md shadow-xl">
                 <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                   <History className="h-4 w-4" />
                   Recent History
                 </h3>
                 <div className="space-y-2 max-h-[400px] overflow-auto pr-2 custom-scrollbar">
                    {sessions.slice(0, 15).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => handleSelectSession(s.id)}
                        className="w-full text-left p-3 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 hover:border-white/20 transition-all group relative overflow-hidden"
                      >
                         <div className="flex justify-between items-center mb-1">
                           <span className="text-[10px] font-mono text-zinc-500">{s.id.slice(0, 8)}</span>
                           <span className={cn(
                             "text-[10px] font-bold uppercase tracking-tighter",
                             s.status === 'running' ? "text-blue-400 animate-pulse" :
                             s.status === 'completed' ? "text-emerald-500" :
                             s.status === 'failed' ? "text-red-500" : "text-zinc-500"
                           )}>
                             {s.status}
                           </span>
                         </div>
                         <div className="text-xs font-medium text-zinc-200 line-clamp-2 group-hover:text-white transition-colors">
                           {s.goal || "Untitled session"}
                         </div>
                         {sessionId === s.id && (
                           <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500" />
                         )}
                      </button>
                    ))}
                 </div>
              </div>
            )}
          </div>
        </div>
      )}

      {view === 'live' && activeSession && (
        <div className="space-y-6 animate-in fade-in zoom-in-95 duration-500">
          {status === 'paused' && (
            <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl flex items-center justify-between backdrop-blur-md shadow-lg">
              <div className="flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-amber-500" />
                <div className="text-amber-500 text-sm font-medium">
                  The agent requires authorization to proceed with a sensitive action.
                </div>
              </div>
              <Button 
                onClick={handleResume} 
                className="bg-amber-500 hover:bg-amber-600 text-black font-bold rounded-xl h-9"
              >
                Authorize & Resume
              </Button>
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
            <Card className="xl:col-span-2 border-white/5 bg-zinc-950 rounded-3xl overflow-hidden shadow-2xl flex flex-col h-[700px]">
              <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02] flex flex-row items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                  <CardTitle className="text-xs font-bold uppercase tracking-widest text-zinc-400">Terminal Log</CardTitle>
                </div>
                <div className="text-[10px] font-mono text-zinc-600">{activeSession.id}</div>
              </CardHeader>
              <CardContent className="flex-1 overflow-y-auto p-6 space-y-4 font-mono text-[13px] custom-scrollbar bg-black/20">
                {events.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-zinc-700 space-y-4">
                    <Terminal className="h-12 w-12 opacity-20" />
                    <p className="italic text-sm">Synchronizing with system environment...</p>
                  </div>
                ) : (
                  events
                    .filter(e => ['agent', 'tools'].includes(e.type))
                    .map((event, i) => (
                    <div key={i} className="group border-l-2 border-white/5 pl-4 py-1 hover:border-blue-500/30 transition-all animate-in fade-in slide-in-from-left-2 duration-300">
                      <div className="flex items-center space-x-3 mb-2">
                        <span className={cn(
                          "px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tight border",
                          event.type === 'agent' ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                          event.type === 'tools' ? "bg-purple-500/10 text-purple-400 border-purple-500/20" :
                          "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                        )}>
                          {event.type}
                        </span>
                        <span className="text-[10px] text-zinc-600 font-medium">{new Date(event.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <div className="p-4 bg-zinc-900/40 rounded-2xl border border-white/[0.03] group-hover:border-white/10 transition-all">
                        <pre className="whitespace-pre-wrap break-all text-zinc-300 leading-relaxed">
                          {typeof event.payload === 'string' 
                            ? event.payload 
                            : JSON.stringify(event.payload, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <div className="space-y-8 flex flex-col h-full">
              <Card className="border-white/5 bg-zinc-900/50 rounded-3xl overflow-hidden shadow-xl flex flex-col max-h-[400px]">
                <CardHeader className="py-2 px-6 border-b border-white/5 bg-white/[0.02] flex flex-row items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <ListTodo className="h-4 w-4 text-blue-500" />
                    <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Autonomous Plan</CardTitle>
                  </div>
                  <div className="flex bg-black/40 p-1 rounded-lg border border-white/5">
                    <button 
                      onClick={() => setPlanTab('checklist')}
                      className={cn(
                        "px-2 py-1 rounded text-[9px] font-bold uppercase transition-all",
                        planTab === 'checklist' ? "bg-white/10 text-white shadow-lg" : "text-zinc-500 hover:text-zinc-300"
                      )}
                    >
                      Checklist
                    </button>
                    <button 
                      onClick={() => setPlanTab('markdown')}
                      className={cn(
                        "px-2 py-1 rounded text-[9px] font-bold uppercase transition-all",
                        planTab === 'markdown' ? "bg-white/10 text-white shadow-lg" : "text-zinc-500 hover:text-zinc-300"
                      )}
                    >
                      Strategy
                    </button>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-3 overflow-y-auto custom-scrollbar">
                  {planSteps.length === 0 && !rawPlan ? (
                    <div className="p-4 bg-black/40 rounded-2xl border border-white/5 italic text-zinc-500 text-xs text-center">
                      Agent is formulating strategy...
                    </div>
                  ) : planTab === 'checklist' ? (
                    planSteps.map((step: PlanStep, idx: number) => (
                      <div key={idx} className={cn(
                        "p-3 rounded-xl border transition-all",
                        step.status === 'completed' ? "bg-emerald-500/5 border-emerald-500/20 opacity-60" :
                        step.status === 'in_progress' ? "bg-blue-500/10 border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.1)]" :
                        "bg-white/5 border-white/5"
                      )}>
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 shrink-0">
                            {step.status === 'completed' ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                            ) : step.status === 'in_progress' ? (
                              <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                            ) : (
                              <Circle className="h-4 w-4 text-zinc-700" />
                            )}
                          </div>
                          <div className="space-y-1">
                            <div className={cn(
                              "text-xs font-bold leading-none",
                              step.status === 'completed' ? "text-emerald-500/80 line-through" :
                              step.status === 'in_progress' ? "text-blue-400" : "text-zinc-400"
                            )}>
                              {step.title}
                            </div>
                            <p className="text-[10px] text-zinc-500 leading-tight">
                              {step.description}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="prose prose-invert prose-xs max-w-none text-zinc-400 font-mono leading-relaxed px-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {rawPlan}
                      </ReactMarkdown>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-white/5 bg-zinc-900/50 rounded-3xl overflow-hidden shadow-xl flex-1 flex flex-col">
                <CardHeader className="py-4 px-6 border-b border-white/5 bg-white/[0.02]">
                  <CardTitle className="text-xs font-bold uppercase tracking-widest text-zinc-500">Visual Environment</CardTitle>
                </CardHeader>
                <CardContent className="flex-1 flex flex-col items-center justify-center bg-black p-0 relative group min-h-[300px]">
                  <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent z-10 flex flex-col justify-end p-8 space-y-2">
                    <h4 className="text-white font-bold text-lg tracking-tight">System Virtualization</h4>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-[0.2em] font-medium flex items-center gap-2">
                      <Terminal className="h-3 w-3" /> 
                      Awaiting Frame Stream...
                    </p>
                  </div>
                  <div className="relative">
                    <div className="w-16 h-16 border-4 border-zinc-900 border-t-blue-500 rounded-full animate-spin shadow-[0_0_20px_rgba(59,130,246,0.2)]"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-8 h-8 bg-blue-500/10 rounded-full blur-xl animate-pulse"></div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              <Button 
                variant="outline" 
                className="w-full h-12 rounded-2xl border-white/5 bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white"
                onClick={() => setView('setup')}
              >
                <Plus className="h-4 w-4 mr-2" />
                Start Another Task
              </Button>
            </div>
          </div>
        </div>
      )}
      
      {view === 'live' && !activeSession && (
        <div className="flex flex-col items-center justify-center py-40 text-center space-y-6">
           <div className="h-24 w-24 rounded-full bg-white/5 flex items-center justify-center border border-white/10 shadow-2xl">
              <Terminal className="h-10 w-10 text-zinc-600" />
           </div>
           <div className="space-y-2">
              <h3 className="text-2xl font-bold text-white tracking-tight">No active deployment</h3>
              <p className="text-zinc-500 text-sm max-w-xs mx-auto">Please select a session from the history or launch a new autonomous agent.</p>
           </div>
           <Button 
            className="rounded-xl h-11 px-8 font-bold bg-zinc-100 text-black hover:bg-white transition-all" 
            onClick={() => setView("setup")}
           >
             Return to Command Center
           </Button>
        </div>
      )}
    </div>
  );
}