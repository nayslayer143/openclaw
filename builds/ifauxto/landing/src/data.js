/**
 * @fileoverview Demo data structure for the marketing landing page.
 * Populates folder structure, photo assets, and suggested tags for the interactive demo.
 */

const DEMO_DATA = {
    /**
     * @type {Array<{id: string, name: string, count: number, color: string}>}
     */
    folders: [
        { id: 'trips', name: '🏞️ Trips', count: 8, color: '#fbbf24' },
        { id: 'family', name: '👨‍👩‍👧‍👦 Family', count: 12, color: '#fbbf24' },
        { id: 'screenshots', name: '📱 Screenshots', count: 6, color: '#fbbf24' },
        { id: 'food', name: '🍕 Food', count: 7, color: '#fbbf24' },
        { id: 'architecture', name: '🏛️ Architecture', count: 5, color: '#fbbf24' }
    ],

    /**
     * @type {Object<string, Array<{id: string, tags: string[], color: string}>>}
     */
    photos: {
        'trips': [
            { id: 't1', tags: ['beach', 'sunset', 'summer', 'vacation'], color: '#3b82f6' }, // 1/8
            { id: 't2', tags: ['mountain', 'hiking', 'adventure', 'day'], color: '#10b981' }, // 2/8
            { id: 't3', tags: ['city', 'night', 'lights', 'evening'], color: '#ef4444' }, // 3/8
            { id: 't4', tags: ['beach', 'goldenhour', 'family'], color: '#f97316' }, // 4/8
            { id: 't5', tags: ['mountain', 'mist', 'earlymorning'], color: '#374151' }, // 5/8
            { id: 't6', tags: ['city', 'day', 'architecture'], color: '#6b72b8' }, // 6/8
            { id: 't7', tags: ['vacation', 'portrait', 'people'], color: '#f59e0b' }, // 7/8
            { id: 't8', tags: ['summer', 'friends', 'outdoor'], color: '#22c55e' } // 8/8
        ],
        'family': [
            { id: 'f1', tags: ['portrait', 'bestfriends', 'smile'], color: '#3b82f6' }, // 1/12
            { id: 'f2', tags: ['group', 'outing', 'fun'], color: '#10b981' }, // 2/12
            { id: 'f3', tags: ['portrait', 'mom', 'loving'], color: '#ef4444' }, // 3/12
            { id: 'f4', tags: ['group', 'birthday', 'celebration'], color: '#f97316' }, // 4/12
            { id: 'f5', tags: ['people', 'portrait', 'formal'], color: '#374151' }, // 5/12
            { id: 'f6', tags: ['outing', 'lake', 'day'], color: '#6b72b8' }, // 6/12
            { id: 'f7', tags: ['portrait', 'sister', 'sisterhood'], color: '#f59e0b' }, // 7/12
            { id: 'f8', tags: ['family', 'together', 'memories'], color: '#22c55e' }, // 8/12
            { id: 'f9', tags: ['outdoor', 'play', 'kids'], color: '#3b82f6' }, // 9/12
            { id: 'f10', tags: ['portrait', 'smile', 'candid'], color: '#10b981' }, // 10/12
            { id: 'f11', tags: ['outdoor', 'nature', 'beautiful'], color: '#ef4444' }, // 11/12
            { id: 'f12', tags: ['group', 'sunset', 'goldenhour'], color: '#f97316' }  // 12/12
        ],
        'screenshots': [
            { id: 's1', tags: ['screenshot', 'text', 'chat'], color: '#9ca3af' }, // 1/6
            { id: 's2', tags: ['screenshot', 'settings', 'ui'], color: '#6b72b8' }, // 2/6
            { id: 's3', tags: ['text', 'notes', 'idea'], color: '#4b5563' }, // 3/6
            { id: 's4', tags: ['screenshot', 'web', 'article'], color: '#374151' }, // 4/6
            { id: 's5', tags: ['ui', 'design', 'mockup'], color: '#1f2937' }, // 5/6
            { id: 's6', tags: ['text', 'info', 'reminder'], color: '#71717a' }  // 6/6
        ],
        'food': [
            { id: 'fo1', tags: ['restaurant', 'finedining', 'dinner'], color: '#d97706' }, // 1/7
            { id: 'fo2', tags: ['coffee', 'latte', 'morning'], color: '#ca8a04' }, // 2/7
            { id: 'fo3', tags: ['sushi', 'japanese', 'seafood'], color: '#059669' }, // 3/7
            { id: 'fo4', tags: ['foodie', 'plate', 'lunch'], color: '#ef4444' }, // 4/7
            { id: 'fo5', tags: ['restaurant', 'italian', 'pasta'], color: '#9240ff' }, // 5/7
            { id: 'fo6', tags: ['coffee', 'art', 'barista'], color: '#84cc16' }, // 6/7
            { id: 'fo7', tags: ['sushi', 'raw', 'japan'], color: '#3b82f6' } // 7/7
        ],
        'architecture': [
            { id: 'a1', tags: ['building', 'skyscraper', 'urban'], color: '#1d4ed8' }, // 1/5
            { id: 'a2', tags: ['bridge', 'view', 'span'], color: '#3b82f6' }, // 2/5
            { id: 'a3', tags: ['interior', 'modern', 'design'], color: '#4b5563' }, // 3/5
            { id: 'a4', tags: ['building', 'historic', 'stone'], color: '#6b72b8' }, // 4/5
            { id: 'a5', tags: ['urban', 'perspective', 'line'], color: '#16a34a' } // 5/5
        ]
    },

    /**
     * @type {Array<string>}
     * A comprehensive list of suggested tags for the UI.
     */
    allTags: [
        'beach', 'mountain', 'city', 'vacation', 'portrait', 'group', 'outdoor', 
        'sunset', 'goldenhour', 'summer', 'hiking', 'adventure', 'smile', 
        'latte', 'coffee', 'sushi', 'building', 'historic'
    ]
};
