import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
	return {
		plugins: [react()],
		server: {
			// Proxy API requests during development to the backend
			proxy: {
				'/upload': {
					target: 'http://backend:8000',
					changeOrigin: true,
					timeout: 6000000,
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
