import { vectorize, ColorMode, Hierarchical, PathSimplifyMode } from './index.js';
import { readFile, writeFile } from 'node:fs/promises';
import { join, parse } from 'node:path';


async function vectorizeImage(imagePath) {
    try {
        const src = await readFile(imagePath);

        const config = {
            colorMode: ColorMode.Color,             // Keep color
            colorPrecision: 8,                      // Reduce color precision to simplify colors
            filterSpeckle: 10,                      // Increase to filter out smaller noise
            spliceThreshold: 10,                    // Increase to simplify complex paths
            cornerThreshold: 100,                   // Smoother corners, less noise
            hierarchical: Hierarchical.Stacked,     // Stack shapes based on their visual hierarchy
            mode: PathSimplifyMode.Spline,          // Keep spline mode for smoother paths
            layerDifference: 5,                     // Slight adjustment for better layer separation
            lengthThreshold: 5000,                  // Increase to ignore smaller paths (noise)
            maxIterations: 1,                       // One iteration to avoid over-smoothing
        };

        const begin = performance.now();
        const result = await vectorize(src, config);
        const end = performance.now();

        console.log(`${imagePath} Vectorization Time: ${(end - begin).toFixed(2)}ms`);

        const { dir, name } = parse(imagePath);
        const outputFilePath = join(dir, `${name}.svg`);

        await writeFile(outputFilePath, result);
        console.log(`SVG file saved: ${outputFilePath}`);
    } catch (error) {
        console.error('Error:', error);
    }
}


async function main() {
    const imagePath = process.argv[2]; // Get the file path from command line arguments

    if (!imagePath) {
        console.error('Please provide a file path as an argument.');
        process.exit(1);
    }

    await vectorizeImage(imagePath);
}


main();
