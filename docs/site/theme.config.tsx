import React from 'react';
import type { DocsThemeConfig } from 'nextra-theme-docs';

const config: DocsThemeConfig = {
  logo: <span className="font-semibold">AstraForge Docs</span>,
  project: {
    link: 'https://github.com/AstraForge/AstraForge'
  },
  docsRepositoryBase: 'https://github.com/AstraForge/AstraForge/tree/main/docs/site',
  footer: {
    content: 'AstraForge documentation'
  },
  head: (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <meta property="og:title" content="AstraForge Docs" />
      <meta property="og:description" content="AstraForge documentation" />
    </>
  ),
  banner: {
    key: 'astra-docs-alpha',
    content: 'Docs are new—share feedback in issues or pull requests.'
  },
  editLink: {
    content: 'Suggest changes to this page'
  },
  feedback: {
    content: 'Question? Open an issue.'
  },
  search: {
    placeholder: 'Search docs...'
  }
};

export default config;
