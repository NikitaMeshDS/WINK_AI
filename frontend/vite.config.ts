import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
	return {
		plugins: [react()],
		server: {
			// Proxy API requests during development to the backend
			proxy: {
				'/upload': { // Keep for compatibility if needed, though it's deprecated
					target: 'http://backend:8000',
					changeOrigin: true,
					timeout: 6000000,
				},
				'/initiate-upload': {
					target: 'http://backend:8000',
					changeOrigin: true,
					timeout: 6000000, // Long timeout for initial upload
				},
				'/stream-results': {
					target: 'http://backend:8000',
					changeOrigin: true,
					timeout: 0, // No timeout for streaming endpoint
				},
				'/history': {
					target: 'http://backend:8000',
					changeOrigin: true,
				},
				'/result': {
					target: 'http://backend:8000',
					changeOrigin: true,
				},
				'/download': {
					target: 'http://backend:8000',
					changeOrigin: true,
				},
			},
		},
		resolve: {
			alias: {},
		},
		css: {
			// Tailwind CSS will handle autoprefixing via PostCSS
		},
		build: {
			outDir: 'dist',
			emptyOutDir: true,
		},
	}
})
