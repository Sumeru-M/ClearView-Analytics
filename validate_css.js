#!/usr/bin/env node

/**
 * CSS Validation Script
 * Verifies that all CSS in frontend/index.html follows design system
 */

const fs = require('fs');
const path = require('path');

// Read the frontend file
const filePath = path.join(__dirname, 'frontend', 'index.html');
const content = fs.readFileSync(filePath, 'utf-8');

// Extract CSS between <style> tags
const styleRegex = /<style>([\s\S]*?)<\/style>/;
const match = content.match(styleRegex);

if (!match) {
  console.error('❌ No <style> tag found in frontend/index.html');
  process.exit(1);
}

const css = match[1];

console.log('🔍 Validating CSS...\n');

// Check 1: All CSS variables are defined in :root
const cssVarUsages = css.match(/var\(--[\w-]+\)/g) || [];
const cssVarDefinitions = css.match(/--[\w-]+:/g) || [];

const usedVars = [...new Set(cssVarUsages.map(v => v.match(/--[\w-]+/)[0]))];
const definedVars = [...new Set(cssVarDefinitions.map(v => v.replace(':', '')))];

console.log(`📊 CSS Variable Usage:`);
console.log(`   Defined: ${definedVars.length}`);
console.log(`   Used: ${usedVars.length}`);
console.log(`   References: ${cssVarUsages.length}`);

let undefinedVars = usedVars.filter(v => !definedVars.includes(v));
if (undefinedVars.length > 0) {
  console.log(`\n⚠️  Undefined variables: ${undefinedVars.join(', ')}`);
} else {
  console.log(`   ✅ All used variables are defined`);
}

// Check 2: No hardcoded colors outside :root
const hexColorPattern = /#[0-9a-fA-F]{6}/g;
const hexColors = css.match(hexColorPattern) || [];
const rootHexCount = (css.match(/:root\{[\s\S]*?\}/)[0].match(hexColorPattern) || []).length;
const nonRootHexCount = hexColors.length - rootHexCount;

console.log(`\n🎨 Color References:`);
console.log(`   Root definitions: ${rootHexCount}`);
console.log(`   Outside :root: ${nonRootHexCount}`);
if (nonRootHexCount > 0) {
  console.log(`   ⚠️  Found hardcoded colors outside design system`);
} else {
  console.log(`   ✅ All colors use design system variables`);
}

// Check 3: Common CSS classes and selectors are defined
const requiredClasses = [
  'shell', 'sidebar', 'main', 'topbar', 'page',
  'card', 'metric', 'btn', 'tab', 'badge',
  'spinner', 'auth-shell'
];

const requiredElements = ['input', 'table']; // Element selectors, not classes

const definedClasses = css.match(/\.[\w-]+\s*\{/g) || [];
const definedClassNames = definedClasses.map(c => c.replace(/[\.\s\{]/g, ''));

const definedElements = css.match(/^(input|select|textarea|table|th|td|tr)/gm) || [];
const definedElementNames = [...new Set(definedElements.map(e => e.trim()))];

console.log(`\n🧩 Required Classes & Selectors:`);
let missingClasses = [];
requiredClasses.forEach(cls => {
  const found = definedClassNames.includes(cls);
  console.log(`   ${found ? '✅' : '❌'} .${cls}`);
  if (!found) missingClasses.push(cls);
});

console.log(`\n📋 Required Element Selectors:`);
requiredElements.forEach(elem => {
  const found = css.includes(`${elem},`) || css.includes(`${elem}{`);
  console.log(`   ${found ? '✅' : '❌'} ${elem}`);
  if (!found) missingClasses.push(elem);
});

// Check 4: Media queries for responsive design
const mediaQueries = css.match(/@media[^{]*\{/g) || [];
console.log(`\n📱 Responsive Design:`);
console.log(`   Media queries: ${mediaQueries.length}`);
mediaQueries.forEach(q => {
  console.log(`   - ${q.trim()}`);
});

// Check 5: Animations
const keyframes = css.match(/@keyframes\s+[\w-]+\s*\{/g) || [];
console.log(`\n✨ Animations:`);
console.log(`   Defined: ${keyframes.length}`);
keyframes.forEach(kf => {
  console.log(`   - ${kf.trim()}`);
});

// Check 6: CSS file size
const minifiedCSS = css.replace(/\s+/g, ' ').trim();
const cssSize = Buffer.byteLength(minifiedCSS, 'utf8');
console.log(`\n📦 CSS Size:`);
console.log(`   Total: ${Math.round(cssSize / 1024)}KB (minified)`);
console.log(`   Lines: ${css.split('\n').length}`);

// Summary
console.log('\n' + '='.repeat(50));
console.log('VALIDATION SUMMARY');
console.log('='.repeat(50));

const issues = undefinedVars.length + nonRootHexCount + missingClasses.length;
if (issues === 0) {
  console.log('✅ CSS VALIDATION PASSED');
  console.log('\nDesign system compliance: 100%');
  console.log('- All variables defined');
  console.log('- All colors use design system');
  console.log('- All required classes present');
  process.exit(0);
} else {
  console.log('⚠️  CSS VALIDATION ISSUES FOUND');
  console.log(`\nTotal issues: ${issues}`);
  if (undefinedVars.length > 0) console.log(`- Undefined variables: ${undefinedVars.length}`);
  if (nonRootHexCount > 0) console.log(`- Hardcoded colors: ${nonRootHexCount}`);
  if (missingClasses.length > 0) console.log(`- Missing classes: ${missingClasses.length}`);
  process.exit(1);
}
