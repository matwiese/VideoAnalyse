/**
 * Einzeldatei-Build: eine HTML-Datei mit allem (JS, CSS, Worker, Daten) zum
 * Herunterladen und Öffnen per Doppelklick. Aufruf: npm run build:standalone
 */
import { defineConfig, mergeConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';
import base from './vite.config';

export default mergeConfig(base, defineConfig({
  plugins: [viteSingleFile()],
  worker: { format: 'iife' }, // klassischer Worker: läuft auch unter file://
  build: { outDir: 'dist-standalone', chunkSizeWarningLimit: 4000 },
}));
