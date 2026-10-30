/**
 * Data Source Configuration
 * The page reads papers and summaries from this repository's `data` branch
 * through raw.githubusercontent.com.
 */

const DATA_CONFIG = {
    /**
     * GitHub repository owner (username)
     */
    repoOwner: 'Eryc123Y',

    /**
     * GitHub repository name
     */
    repoName: 'daily-arXiv-ai-enhanced',

    /**
     * Data branch name
     * Default: 'data'
     */
    dataBranch: 'data',

    /**
     * Categories the crawl covers; cross-lists from any other primary
     * category are grouped as "Other fields" on the page
     */
    mainCategories: ['cs.CV', 'cs.AI', 'cs.LG', 'cs.CL', 'stat.ML', 'cs.GR'],

    /**
     * Get the base URL for raw GitHub content from data branch
     * @returns {string} Base URL for raw GitHub content
     */
    getDataBaseUrl: function() {
        return `https://raw.githubusercontent.com/${this.repoOwner}/${this.repoName}/${this.dataBranch}`;
    },

    /**
     * Get the full URL for a data file
     * @param {string} filePath - Relative path to the data file (e.g., 'data/2025-01-01.jsonl')
     * @returns {string} Full URL to the data file
     */
    getDataUrl: function(filePath) {
        return `${this.getDataBaseUrl()}/${filePath}`;
    }
};

