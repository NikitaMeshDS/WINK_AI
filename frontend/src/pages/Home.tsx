import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import UploadForm from '../components/UploadForm';
import TableDisplay from '../components/TableDisplay';
import { initiateUpload, UploadDetail, SceneData } from '../api';
import CanvasDisplay from '../components/CanvasDisplay';

type AppStatus = 'idle' | 'uploading' | 'streaming' | 'completed' | 'error';

const Home: React.FC = () => {
  const [status, setStatus] = useState<AppStatus>('idle');
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [scenes, setScenes] = useState<SceneData[]>([]);
  const [finalResult, setFinalResult] = useState<UploadDetail | null>(null);
  const [showCanvas, setShowCanvas] = useState(false);
  const [showName, setShowName] = useState('');

  useEffect(() => {
    // Clean up event source if component unmounts
    let eventSource: EventSource | null = null;
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    handleReset();
    setStatus('uploading');
    setProgressMessage('Uploading file...');
    setError(null);
    setShowName(file.name.split('.').slice(0, -1).join('.'));

    try {
      const { id: uploadId } = await initiateUpload(file);
      
      setStatus('streaming');
      setProgressMessage('Analyzing script...');
      
      const eventSource = new EventSource(`/stream-results/${uploadId}`);
      
      eventSource.onmessage = (event) => {
        const scene = JSON.parse(event.data);
        setScenes((prevScenes) => [...prevScenes, scene]);
      };

      eventSource.addEventListener('done', (event) => {
        const finalData = JSON.parse(event.data);
        setFinalResult(finalData);
        setStatus('completed');
        setProgressMessage(null);
        eventSource.close();
      });

      eventSource.onerror = (err) => {
        console.error('EventSource failed:', err);
        setError('An error occurred during analysis.');
        setStatus('error');
        setProgressMessage(null);
        eventSource.close();
      };

    } catch (err: any) {
      setError(err.message || 'File upload failed.');
      setStatus('error');
      setProgressMessage(null);
    }
  }, []);

  const handleReset = () => {
    setStatus('idle');
    setProgressMessage(null);
    setError(null);
    setScenes([]);
    setFinalResult(null);
    setShowCanvas(false);
    setShowName('');
  };

  const formattedData = useMemo(() => {
    if (scenes.length === 0) {
      return {};
    }
    const groupedBySeries = scenes.reduce((acc, scene) => {
      const seriesName = scene['Серия'] || 'Unknown Series';
      if (!acc[seriesName]) {
        acc[seriesName] = [];
      }
      acc[seriesName].push(scene);
      return acc;
    }, {} as Record<string, SceneData[]>);

    return { [showName]: groupedBySeries };
  }, [scenes, showName]);

  const renderContent = () => {
    switch (status) {
      case 'idle':
      case 'error':
        return (
          <motion.div
            key="upload"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.3 }}
          >
            <UploadForm
              onUpload={handleUpload}
              isLoading={status === 'uploading' || status === 'streaming'}
              progressMessage={progressMessage}
              error={error}
            />
          </motion.div>
        );
      case 'uploading':
      case 'streaming':
      case 'completed':
        return (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-6 bg-card/50 border rounded-2xl p-8"
          >
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <h2 className="text-3xl font-bold tracking-tight">
                {status === 'completed' ? 'Analysis Complete' : 'Analysis in Progress...'}
              </h2>
              <div className="flex items-center gap-4">
                {finalResult?.download_url && (
                  <a
                    href={finalResult.download_url}
                    className="px-4 py-2 text-sm font-semibold text-primary-foreground bg-primary rounded-full shadow-lg"
                  >
                    Download Excel
                  </a>
                )}
                <button
                  onClick={() => setShowCanvas((prev) => !prev)}
                  className="px-4 py-2 text-sm font-semibold border rounded-full"
                >
                  {showCanvas ? 'Table View' : 'Canvas View'}
                </button>
                <button
                  onClick={handleReset}
                  className="px-4 py-2 text-sm font-semibold border rounded-full"
                >
                  Start Over
                </button>
              </div>
            </div>
            {scenes.length > 0 ? (
              showCanvas ? (
                <CanvasDisplay data={formattedData} />
              ) : (
                <TableDisplay data={formattedData} />
              )
            ) : (
              <div className="flex flex-col items-center justify-center h-64">
                 <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <p className="mt-4 text-lg font-semibold">{progressMessage}</p>
              </div>
            )}
          </motion.div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-8 text-center">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 className="text-4xl font-bold tracking-tight lg:text-6xl">
          Unlock Your Story's Potential
        </h1>
        <p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
          Upload your script, and let our AI provide you with a detailed
          breakdown and analysis.
        </p>
      </motion.div>

      <AnimatePresence mode="wait">
        {renderContent()}
      </AnimatePresence>
    </div>
  );
};

export default Home;