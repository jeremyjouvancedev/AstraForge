import React from 'react';
import type { DocsThemeConfig } from 'nextra-theme-docs';

const config: DocsThemeConfig = {
  logo: <span className="font-semibold">AstraForge Docs</span>,
  project: {
    link: 'https://github.com/AstraForge/AstraForge'
  },
  docsRepositoryBase: 'https://github.com/AstraForge/AstraForge/tree/main/docs/site',
  footer: {
    text: 'AstraForge documentation'
  },
  useNextSeoProps() {
    return {
      titleTemplate: '%s | AstraForge Docs'
    };
  },
  banner: {
    key: 'astra-docs-alpha',
    text: 'Docs are new—share feedback in issues or pull requests.'
  },
  editLink: {
    text: 'Suggest changes to this page'
  },
  feedback: {
    content: 'Question? Open an issue.'
  },
  search: {
    placeholder: 'Search docs...'
  }
};

export default config;
