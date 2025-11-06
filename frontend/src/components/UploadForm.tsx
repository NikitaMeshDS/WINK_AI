import React, { useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { uploadScript, UploadResponse } from '../api';

interface UploadFormProps {
  onUploadComplete: (data: UploadResponse) => void;
}

const UploadForm: React.FC<UploadFormProps> = ({ onUploadComplete }) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file || !file.name.toLowerCase().endsWith('.zip')) {
        setError('Please select a valid ZIP archive.');
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const data = await uploadScript(file);
        onUploadComplete(data);
      } catch (err: any) {
        setError(err.message || 'File upload failed.');
      } finally {
        setIsLoading(false);
      }
    },
    [onUploadComplete],
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
            accept=".zip"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleChange}
            disabled={isLoading}
          />
          <div className="space-y-2">
            <p className="text-lg font-semibold">
              Drag & Drop your ZIP file here
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
          </div>
        </motion.div>
        {error && <p className="text-destructive text-sm">{error}</p>}
        {isLoading && (
          <p className="text-muted-foreground">Processing your file...</p>)
        }
      </form>
    </motion.div>
  );
};

export default UploadForm;