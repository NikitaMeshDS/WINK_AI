import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import UploadForm from '../components/UploadForm';
import TableDisplay from '../components/TableDisplay';
import { UploadResponse } from '../api';
import CanvasDisplay from '../components/CanvasDisplay';

const Home: React.FC = () => {
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [showCanvas, setShowCanvas] = useState(false);

  const handleUploadComplete = (data: UploadResponse) => {
    setResult(data);
    setShowCanvas(false);
  };

  const handleReset = () => {
    setResult(null);
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
        {!result ? (
          <motion.div
            key="upload"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.3 }}
          >
            <UploadForm onUploadComplete={handleUploadComplete} />
          </motion.div>
        ) : (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-6 bg-card/50 border rounded-2xl p-8"
          >
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <h2 className="text-3xl font-bold tracking-tight">
                Analysis Complete
              </h2>
              <div className="flex items-center gap-4">
                <a
                  href={`/download/${result.id}`}
                  className="px-4 py-2 text-sm font-semibold text-primary-foreground bg-primary rounded-full shadow-lg"
                >
                  Download Excel
                </a>
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
            {showCanvas ? (
              <CanvasDisplay data={result.data} />
            ) : (
              <TableDisplay data={result.data} />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Home;