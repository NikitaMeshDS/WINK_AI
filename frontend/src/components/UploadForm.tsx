import React, { useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

interface UploadFormProps {
  onUpload: (file: File) => void;
  isLoading: boolean;
  progressMessage: string | null;
  error: string | null;
}

const UploadForm: React.FC<UploadFormProps> = ({ onUpload, isLoading, progressMessage, error }) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      const isAccepted = file && (file.name.toLowerCase().endsWith('.zip') || file.name.toLowerCase().endsWith('.docx'));
      if (!isAccepted) {
        // This component doesn't set the error state directly anymore,
        // but we can call a prop or let the parent handle it.
        // For now, we just prevent the upload.
        alert('Please select a valid .zip or .docx file.');
        return;
      }
      onUpload(file);
    },
    [onUpload],
  );

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === 'dragenter' || e.type === 'dragover');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files?.[0]) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-2xl mx-auto"
    >
      <form
        onSubmit={(e) => e.preventDefault()}
        className="space-y-6 text-center"
        onDragEnter={handleDrag}
      >
        <motion.div
          className={`relative flex flex-col items-center justify-center w-full h-80 rounded-2xl border-2 border-dashed transition-colors ${
            dragActive ? 'border-primary bg-primary/10' : 'border-border'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          whileHover={{ scale: 1.02 }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,.docx"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleChange}
            disabled={isLoading}
          />
          <div className="space-y-2">
            {isLoading ? (
              <div className="flex flex-col items-center space-y-2">
                <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <p className="text-lg font-semibold">{progressMessage || 'Processing...'}</p>
                <p className="text-sm text-muted-foreground">This might take a few moments...</p>
              </div>
            ) : (
              <>
                <p className="text-lg font-semibold">
                  Drag & Drop your .zip or .docx file here
                </p>
                <p className="text-muted-foreground">or</p>
                <motion.button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="px-6 py-2 font-semibold text-primary-foreground bg-primary rounded-full shadow-lg"
                >
                  Browse File
                </motion.button>
              </>
            )}
          </div>
        </motion.div>
        {error && <p className="text-destructive text-sm">{error}</p>}
      </form>
    </motion.div>
  );
};

export default UploadForm;