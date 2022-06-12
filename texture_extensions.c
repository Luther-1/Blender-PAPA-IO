// The MIT License
// 
// Copyright (c) 2021, 2022     Marcus Der      marcusder@hotmail.com
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include<omp.h>
#include<stdlib.h>
#include<stdio.h>
#include<math.h>
#include<string.h>

#define OUTSIDE_IMAGE(x,y,w,h) (x < 0 || x >= w || y < 0 || y >= h)
#define IMAGE_INDEX(x,y,w) ((y) * (w) + x)
#define CLAMP(val,min,max) ((val < min) ? (min) : ((val > max) ? (max) : (val)))

typedef struct LineData {
    float xStart;
    float yStart;
    float xEnd;
    float yEnd;
    float thickness;
    float blur;

} LineData;

typedef struct IslandLines {
    int numLines;
    int islandIdx;
    LineData* lineData;

} IslandLines;

typedef struct Island {
    int numTriangles;
    float* triangles;
} Island;

typedef struct ImageData {
    int width;
    int height;
    float* scratch;
} ImageData;

typedef struct ShortPair {
    short x;
    short y;
} ShortPair;

typedef struct ThreadData {
    float* scratch;
    ShortPair topLeft;
    ShortPair bottomRight;
} ThreadData;

typedef struct BitmaskData {
    unsigned long long* bitmask;
    unsigned long long* dilatedBitmask;
} BitmaskData;

typedef struct EdgeAwareData {
    unsigned long long* bitmask;
    unsigned long long maskIdx;
    void (*writeFunc)(int, int, int, int, void*, void*);
    void* argData;
} EdgeAwareData;

typedef struct EmbeddedWriteData {
    void (*writeFunc)(int, int, int, int, void*, void*);
    void* argData;
} EmbeddedWriteData;

typedef struct BrushData {
    void* brush;
    short brushWidth;
    short brushHeight;
} BrushData;

void clearThreadData(ThreadData* data);

ThreadData* createThreadData(int numThreads, ImageData* imgData) {
    int width = imgData->width;
    int height = imgData->height;
    ThreadData* data = (ThreadData*) malloc(numThreads * sizeof(ThreadData));
    for(int i =0;i<numThreads;i++) {
        // worst case scenario is two perfectly vertical lines, which this holds exactly
        data[i].scratch = calloc(width * height, sizeof(float));
        clearThreadData(data + i);
    }
    return data;
    
}

BitmaskData* createBitmaskData(int width, int height) {
    unsigned long long* bitmask = malloc(width * height * sizeof(unsigned long long));
    unsigned long long* dilatedBitmask = malloc(width * height * sizeof(unsigned long long));
    BitmaskData* data = malloc(sizeof(BitmaskData));
    data->bitmask=bitmask;
    data->dilatedBitmask=dilatedBitmask;
    return data;
}

IslandLines* convertLineData(float* data, int numLines) {
    IslandLines* lines = (IslandLines*) malloc(sizeof(IslandLines) * numLines);
    int idx = 0;

    for(int i = 0; i < numLines; i++) {
        int numData = (int) (data[idx++] + 0.5f);
        int maskIdx = ((int) (data[idx++] + 0.5f)) % 64;

        lines[i] = (IslandLines) {numData, maskIdx, (LineData*)(data + idx)}; // evil
        idx += numData * 6;
    }

    return lines;
}

Island* convertIslandData(float* islandData, int numIslands) {
    Island* islands =  (Island*) malloc(sizeof(Island) * numIslands);
    int idx = 0;

    for(int i =0;i<numIslands;i++) {
        int numTriangles = islandData[idx++];

        islands[i] = (Island) {numTriangles, islandData + idx};
        idx += numTriangles * 6;
    }

    return islands;
}

ImageData* createImageData(int width, int height) {
    ImageData* img = (ImageData*) malloc(sizeof(ImageData));
    img->width=width;
    img->height=height;
    img->scratch = calloc(width * height, sizeof(float));
    return img;
}

BrushData* createBrushDataFloat(float thickness) {
    BrushData* data = (BrushData*) malloc(sizeof(BrushData));
    int width = floor(thickness + 1) * 2 + 1; // add 1 so we can sample easier later
    int height = width;
    data->brushWidth = width;
    data->brushHeight = height;
    
    float* brush = (float*) malloc(sizeof(float) * width * height);
    data->brush = brush;

    int cx = width / 2;
    int cy = height / 2;

    for( int y = 0;y < height; y++) {
        for(int x = 0;x < width; x++) {
            int tx = x - cx;
            int ty = y - cy;
            float dist = thickness - sqrtf(ty*ty + tx*tx);
            float val = CLAMP(dist, 0.0f, 1.0f);
            int idx = IMAGE_INDEX(x,y,width);
            brush[idx] = val;
        }
    }
    return data;
}

void freeBrushData(BrushData* data) {
    free(data->brush);
    free(data);
}

void writeFourFloat(int x, int y, int w, int h, void* _data, void* _dst) {
    
    float* dst = (float*)_dst;
    float* data = (float*)_data;

    int index = IMAGE_INDEX(x,y,w) * 4;
    dst[index + 0] = data[0];
    dst[index + 1] = data[1];
    dst[index + 2] = data[2];
    dst[index + 3] = data[3];
}

void writeSingleFloat(int x, int y, int w, int h, void* _data, void* _dst) {
    float* dst = (float*)_dst;
    float data = *((float*)_data);

    int index = IMAGE_INDEX(x,y,w);
    dst[index] = data;
}

void writeSingleChar(int x, int y, int w, int h, void* _data, void* _dst) {
    char* dst = (char*)_dst;
    char data = *((char*)_data);

    int index = IMAGE_INDEX(x,y,w);
    dst[index] = data;
}

void write3x3Plus(int x, int y, int w, int h, void* _data, void* _dst) {
    EmbeddedWriteData* data = (EmbeddedWriteData*)_data;
    void (*writeFunc)(int, int, int, int, void*, void*) = data->writeFunc;
    void* argData = data->argData;

    const int offsetX[5] = {0,0,-1,1,0};
    const int offsetY[5] = {0,-1,0,0,1};
    
    for(int j=0;j<5;j++) {
        const int ox = x+offsetX[j];
        const int oy = y+offsetY[j];

        if(OUTSIDE_IMAGE(ox,oy,w,h)) {
            continue;
        }
        (*writeFunc)(ox, oy, w, h, argData, _dst);
    }
}

void orSingleULL(int x, int y, int w, int h, void* _data, void* _dst) {
    unsigned long long* dst = (unsigned long long*)_dst;
    unsigned long long data = *((unsigned long long*)_data);

    int index = IMAGE_INDEX(x,y,w);
    dst[index] |= data;
}

void writeEdgeAware(int x, int y, int w, int h, void* _data, void* _dst) {
    // for each neighbor, if any of their neighbors are not in the mask, draw to that pixel.
    // runs 16 times per pixel.
    const int offsetX[4] = {0,-1,1,0};
    const int offsetY[4] = {-1,0,0,1};

    EdgeAwareData* data = (EdgeAwareData*)_data;
    unsigned long long* bitmask = data->bitmask;
    unsigned long long maskIdx = data->maskIdx;
    unsigned long long invMaskIdx = ~maskIdx;
    void (*writeFunc)(int, int, int, int, void*, void*) = data->writeFunc;

    int j, k;
    for(j=0;j<4;j++) {
        const int lx = x+offsetX[j];
        const int ly = y+offsetY[j];
        if(OUTSIDE_IMAGE(lx,ly,w,h)) {
            continue;
        }
        // TODO: this sometimes doesn't work?
        const int idx = IMAGE_INDEX(lx,ly,w);
        if(bitmask[idx] & invMaskIdx) {
            continue;
        }

        for(k=0;k<4;k++) {
            const int lx2 = lx+offsetX[k];
            const int ly2 = ly+offsetY[k];
            if(OUTSIDE_IMAGE(lx2,ly2,w,h)) {
                (*writeFunc)(lx, ly, h, w, data->argData, _dst);
                break;
            }

            const int idx2 = IMAGE_INDEX(lx2,ly2,w);
            if(!(bitmask[idx2] & maskIdx)) {
                (*writeFunc)(lx, ly, h, w, data->argData, _dst);
                break;
            }
        }
    }
}

inline float linearSampleBrush(float brushX, float brushY, float* brush, int brushWidth, int invert) { // assumed this is always in range.
    int bx = (int) brushX;
    int by = (int) brushY;
    float fx = brushX - bx;
    float fy = brushY - by;

    int idx1 = IMAGE_INDEX(bx,by,brushWidth);
    int idx2 = idx1 + brushWidth;
    if(invert) {
        float lerp1 = brush[idx1] * fx + brush[idx1 + 1] * (1 - fx);
        float lerp2 = brush[idx2] * fx + brush[idx2 + 1] * (1 - fx);
        return lerp1 * fy + lerp2 * (1 - fy);
    }
    float lerp1 = brush[idx1] * (1 - fx) + brush[idx1 + 1] * fx;
        float lerp2 = brush[idx2] * (1 - fx) + brush[idx2 + 1] * fx;
        return lerp1 * (1 - fy) + lerp2 * fy;

    
    
}

void writeSingleFloatBrush(float x, float y, int w, int h, void* _data, void*_dst) {
    BrushData* data = (BrushData*) _data;
    int brushWidth = data->brushWidth;
    int brushHeight = data->brushHeight;

    int hw = brushWidth / 2;
    int hh = brushHeight / 2;

    float* dst = (float*)_dst;

    int yStart = (int)y - hh;
    int xStart = (int)x - hw;

    float fx = x - ((int) x);
    float fy = y - ((int) y);

    for(int y2 = yStart + 1;y2 < yStart + brushWidth - 1;y2++) {
        for(int x2 = xStart + 1;x2 < xStart + brushWidth - 1;x2++) { 
            if(OUTSIDE_IMAGE(x2,y2,w,h)) {
                continue;
            }
            float brushX = x2 - xStart;
            float brushY = y2 - yStart;

            // Both of these methods produce a slightly offset result. Peform it in both directions to fix.
            float v1 = linearSampleBrush(brushX - fx, brushY - fy, (float*)data->brush, brushWidth, 0);
            float v2 = linearSampleBrush(brushX + fx, brushY + fy, (float*)data->brush, brushWidth, 1);
            float v3 = __max(v1,v2);
            int imageIdx = IMAGE_INDEX(x2,y2,w);
            float v4 = dst[imageIdx];
            dst[imageIdx] = __max(v3,v4);
        }
    }
}

void freeStructData(BitmaskData* bitmask, IslandLines* lines1, IslandLines* lines2, Island* islands, ThreadData* threadData, int numThreads, ImageData* imageData) {
    free(bitmask->bitmask);
    free(bitmask->dilatedBitmask);
    free(bitmask);
    free(lines1);
    free(lines2);
    free(islands);
    for(int i =0;i<numThreads;i++) {
        free(threadData[i].scratch);
    }
    free(threadData);
    free(imageData->scratch);
    free(imageData);
}

void setPixel(float* dst, int x, int y, int w, float r, float g, float b, float a) {
    int index = (y * w + x) << 2;
    dst[index] = r;
    dst[index + 1] = g;
    dst[index + 2] = b;
    dst[index + 3] = a;
}

int pixelSet(float* dst, int x, int y, int w, int h) {
    if(OUTSIDE_IMAGE(x,y,w,h))
        return 0;
    return dst[(y * w + x) << 2] != 0;
}

int pixelSetMask(char* buf, int x, int y, int w, int h) {
    if(OUTSIDE_IMAGE(x,y,w,h))
        return 0;
    return buf[y * w + x] != 0;
}

int pixelSetMaskBoundary(char* buf, int x, int y, int w, int h) {
    if(OUTSIDE_IMAGE(x,y,w,h))
        return 1;
    return buf[y * w + x] != 0;
}

float gaussian(float x, float fac) {
    return 1 / (sqrt(2.0*3.1415926)) * exp(-2*(x*x)/(fac*fac));
}

float* buildKernel(int kw, float blur) {
    float* kernel = calloc(kw,sizeof(float));
    int kc = kw/2;

    float sum = 0;
    for (int x=0;x<kw;x++) {
        float d = gaussian(kc-x, blur);
        sum+=d;
        kernel[x] = d;
    }
    for (int x=0;x<kw;x++) {
        kernel[x]/=sum;
    }
    return kernel;
}

int reflect(int M, int x) {
    if(x<0) {
        return -x-1;
    }
    if (x >= M) {
        return 2 * M - x - 1;
    }
    return x;
}

void drawLine(void* dst, int x0, int y0, int x1, int y1, int imgWidth, int imgHeight, void* data, void (*writeFunc)(int, int, int, int, void*, void*)) {
    // https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm
    int dx = abs(x1-x0);
    int sx = x0<x1 ? 1 : -1;
    int dy = -abs(y1-y0);
    int sy = y0<y1 ? 1 : -1;
    int err = dx + dy;
    int e2;
    while(1) {
        (*writeFunc)(x0,y0, imgWidth, imgHeight, data, dst);
        if(x0 == x1 && y0 == y1) {
            break;
        }
        e2 = 2 * err;
        if(e2 >= dy) {
            err += dy;
            x0 += sx;
        }
        if(e2 <= dx) {
            err += dx;
            y0 += sy;
        }
    }
}

void drawLineFloat(void* dst, float x0, float y0, float x1, float y1, int imgWidth, int imgHeight, 
                    float spacing, void*data, void (*writeFunc)(float, float, int, int, void*, void*)) {
    float dist = sqrtf( powf(x1 - x0, 2) + powf(y1 - y0, 2) );
    int iterations = (int) ceil(dist / spacing);
    float dx = (x1 - x0) / (float)iterations;
    float dy = (y1 - y0) / (float)iterations;

    float cx = x0;
    float cy = y0;

    for(int i =0; i < iterations; i++) {
        (*writeFunc)(cx,cy, imgWidth, imgHeight, data, dst);
        cx+=dx;
        cy+=dy;
    }
}

void fillBottomFlatTriangle(void* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, int imgHeight, 
                            void* data, void (*writeFunc)(int, int, int, int, void*, void*)) {
    float invSlope1 = (float)(x1 - x0) / (float)(y1 - y0);
    float invSlope2 = (float)(x2 - x0) / (float)(y2 - y0);

    float cx1 = x0;
    float cx2 = x0;

    for (int y=y0; y<=y2; y++) {
        drawLine(dst, cx1, y, cx2, y, imgWidth, imgHeight, data, writeFunc);
        cx1+=invSlope1;
        cx2+=invSlope2;
    }
}

void fillTopFlatTriangle(void* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, int imgHeight,
                         void* data, void (*writeFunc)(int, int, int, int, void*, void*)) {
    float invSlope1 = (float)(x2 - x0) / (float)(y2 - y0);
    float invSlope2 = (float)(x2 - x1) / (float)(y2 - y1);

    float cx1 = x2;
    float cx2 = x2;

    for (int y=y2; y>=y0; y--) {
        drawLine(dst, cx1, y, cx2, y, imgWidth, imgHeight, data, writeFunc);
        cx1-=invSlope1;
        cx2-=invSlope2;
    }
}

void drawTriangle(  void* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, int imgHeight, 
                    void* data, void (*writeFunc)(int, int, int, int, void*, void*)) {
    // http://www.sunshine2k.de/coding/java/TriangleRasterization/TriangleRasterization.html
    int y[3];
    int x[3];

    if(y0==y1 && y1==y2) {
        return;
    }

    // quick hard coded sort
    if(y0 <= y1 && y0 <= y2) { // y0 smallest
        if(y1 <=y2) {
            y[0] = y0; y[1] = y1; y[2] = y2; x[0] = x0; x[1] = x1; x[2] = x2;
        } else {
            y[0] = y0; y[1] = y2; y[2] = y1; x[0] = x0; x[1] = x2; x[2] = x1;
        }
    } else if(y1 <= y0 && y1 <= y2) { // y1 smallest
        if(y0<=y2) {
            y[0] = y1; y[1] = y0; y[2] = y2; x[0] = x1; x[1] = x0; x[2] = x2;
        } else {
            y[0] = y1; y[1] = y2; y[2] = y0; x[0] = x1; x[1] = x2; x[2] = x0;
        }
    } else { // y2 smallest
        if(y0 <= y1) {
            y[0] = y2; y[1] = y0; y[2] = y1; x[0] = x2; x[1] = x0; x[2] = x1;
        } else {
            y[0] = y2; y[1] = y1; y[2] = y0; x[0] = x2; x[1] = x1; x[2] = x0;
        }
    }

    if(y[1] == y[2]) {
        fillBottomFlatTriangle(dst,x[0],y[0],x[1],y[1],x[2],y[2],imgWidth, imgHeight, data, writeFunc);
    } else if(y[0] == y[1]) {
        fillTopFlatTriangle(dst,x[0],y[0],x[1],y[1],x[2],y[2],imgWidth, imgHeight, data, writeFunc);
    } else {
        int x3 = (int)(x[0] + ((float)(y[1] - y[0]) / (float)(y[2] - y[0])) * (x[2] - x[0]));
        int y3 = y[1];
        fillBottomFlatTriangle(dst,x[0],y[0],x[1],y[1],x3,y3,imgWidth, imgHeight, data, writeFunc);
        fillTopFlatTriangle(dst,x[1],y[1],x3,y3,x[2],y[2],imgWidth, imgHeight, data, writeFunc);
    }
}

void clearThreadData(ThreadData* threadData) {
    threadData->topLeft.x=SHRT_MAX;
    threadData->topLeft.y=SHRT_MAX;
    threadData->bottomRight.x=0;
    threadData->bottomRight.y=0;
}

void constrainArea(ImageData* imageData, ThreadData* threadData) {
    int width = imageData->width;
    int height = imageData->height;
    
    ShortPair topLeft =     threadData->topLeft;
    ShortPair bottomRight = threadData->bottomRight;

    int xmin = CLAMP(topLeft.x,0,width - 1);
    int xmax = CLAMP(bottomRight.x,0,width);

    int ymin = CLAMP(bottomRight.y,0,height - 1);
    int ymax = CLAMP(topLeft.y,0,height);

    threadData->topLeft.x = xmin;
    threadData->bottomRight.x = xmax;

    threadData->topLeft.y = ymax;
    threadData->bottomRight.y = ymin;
}

void copyAndClearThreadScratch(BitmaskData* BitmaskData, unsigned long long maskIdx, ThreadData* threadData, ImageData* info, float multiplier) {
    int width = info->width;
    float* dst = info->scratch;
    float* src = threadData->scratch;

    unsigned long long* dilatedBitmask = BitmaskData->dilatedBitmask;

    constrainArea(info, threadData);

    ShortPair topLeft =     threadData->topLeft;
    ShortPair bottomRight = threadData->bottomRight;

    int xmin = topLeft.x;
    int xmax = bottomRight.x;

    int ymin = bottomRight.y;
    int ymax = topLeft.y;

    for(int y = ymin; y<ymax; y++) {
        for(int x = xmin; x<xmax; x++) {
            int idx = IMAGE_INDEX(x,y,width);
            if(dilatedBitmask[idx] & maskIdx) {
                // #pragma omp atomic write
                float val = src[idx] * multiplier;
                float max = __max(dst[idx], val);
                dst[idx] = CLAMP(max, 0.0, 1.0);
            }
            src[idx] = 0;
        }
    }
}

void fixMaskHoles(unsigned long long* mask, ImageData* data) {
    int width = data->width;
    int height = data->height;
    const int offsetX[4] = {0,-1,1,0};
    const int offsetY[4] = {-1,0,0,1};
    int j;
    for(int y =0;y<height;y++) {
        for(int x=0;x<width;x++) {
            unsigned long long test = -1; // all 1s
            for(j=0;j<4;j++) {
                if(!OUTSIDE_IMAGE(x+offsetX[j],y+offsetY[j],width,height)) {
                    test &= mask[IMAGE_INDEX(x,y,width)];
                }
            }
            mask[IMAGE_INDEX(x,y,width)] |= test;
        }
    }
}

void generateBitmask(BitmaskData* bitmaskData, ImageData* data, Island* islands, int startIdx, int endIdx) {
    // clear the bitmask
    unsigned long long* bitmask = bitmaskData->bitmask;
    unsigned long long* dilatedBitmask = bitmaskData->dilatedBitmask;
    memset(bitmask,0,data->width * data->height * sizeof(unsigned long long));
    memset(dilatedBitmask,0,data->width * data->height * sizeof(unsigned long long));

    float fwidth = (float)data->width;
    float fheight = (float)data->height;
    const float subtract = 0.0f;

    //#pragma omp parallel for
    for( int i=startIdx; i<endIdx; i++ ) {
        Island island = islands[i];
        int num = island.numTriangles * 6;
        unsigned long long val[1] = {1ULL<<(i-startIdx)};
        EmbeddedWriteData writeData;
        writeData.writeFunc = orSingleULL;
        writeData.argData = val;
        for(int k = 0;k<num;k+=6) {
            int x0 = abs((int)(island.triangles[k] * fwidth - subtract));
            int y0 = abs((int)(island.triangles[k + 1] * fheight - subtract));
            int x1 = abs((int)(island.triangles[k + 2] * fwidth - subtract));
            int y1 = abs((int)(island.triangles[k + 3] * fheight - subtract));
            int x2 = abs((int)(island.triangles[k + 4] * fwidth - subtract));
            int y2 = abs((int)(island.triangles[k + 5] * fheight - subtract));
            drawTriangle( (void*)bitmask, x0, y0, x1, y1, x2, y2, data->width, data->height, val, orSingleULL );
            drawLine( (void*)bitmask, x0, y0, x1, y1, data->width, data->height, &writeData, write3x3Plus );
            drawLine( (void*)bitmask, x1, y1, x2, y2, data->width, data->height, &writeData, write3x3Plus );
            drawLine( (void*)bitmask, x2, y2, x0, y0, data->width, data->height, &writeData, write3x3Plus );
        }
    }
    // fixMaskHoles(bitmask, data);

    // generate dilated bitmask

    int width = data->width;
    int height = data->height;

    #pragma omp parallel for collapse(2)
    for ( int x=0; x<width; x++ ) {
        for ( int y=0; y<height; y++ ) {
            int idx = IMAGE_INDEX(x,y,width);

            // only allow it to bleed outwards to pixels that are not already occupied
            if(bitmask[idx]) {
                dilatedBitmask[idx] = bitmask[idx];
            } else {
                unsigned long long val = 0;
                for(int j=0;j<9;j++) {
                    int ox = x+j % 3 - 1;
                    int oy = y+j / 3 - 1;

                    if(OUTSIDE_IMAGE(ox,oy,width,height)) {
                        continue;
                    }

                    int idx = IMAGE_INDEX(ox,oy,width);
                    val |= bitmask[idx];
                }
                
                dilatedBitmask[idx] = val;
            }
        }
    }
}

void drawLineSegmentEdgeAware(unsigned long long* bitmask, unsigned long long maskIdx, LineData* lineData, ImageData* imageData, ThreadData* threadData) {

    float fwidth = imageData->width;
    float fheight = imageData->height;

    const float subtract = 0.0f;
    const float colour[1] = {1.0f};

    LineData data = *lineData;
    int x0 = abs((int)(data.xStart * fwidth - subtract));
    int y0 = abs((int)(data.yStart * fheight - subtract));
    int x1 = abs((int)(data.xEnd * fwidth - subtract));
    int y1 = abs((int)(data.yEnd * fheight - subtract));

    int minX = __min(x0,x1);
    int maxX = __max(x0,x1);

    int minY = __min(y0,y1);
    int maxY = __max(y0,y1);

    threadData->topLeft.x=minX - 2;
    threadData->topLeft.y=maxY + 2;

    threadData->bottomRight.x=maxX + 2;
    threadData->bottomRight.y=minY - 2;

    EdgeAwareData argData;
    argData.bitmask = bitmask;
    argData.maskIdx = maskIdx;
    argData.writeFunc = writeSingleFloat;
    argData.argData = (void*)colour;

    drawLine( threadData->scratch, x0, y0, x1, y1, imageData->width, imageData->height, (void*)(&argData), writeEdgeAware );
    // drawLine( threadData->scratch, x1, y1, x0, y0, imageData->width, imageData->height, (void*)(&argData), writeEdgeAware );
}

void drawLineSegmentThickness(LineData* lineData, ImageData* imageData, ThreadData* threadData) {

    float fwidth = imageData->width;
    float fheight = imageData->height;

    LineData data = *lineData;
    float x0 = data.xStart * fwidth;
    float y0 = data.yStart * fheight;
    float x1 = data.xEnd * fwidth;
    float y1 = data.yEnd * fheight;
    float thickness = data.thickness;
    BrushData* brushData = createBrushDataFloat(thickness);

    int ceilThickness = ceil(thickness + 1);

    threadData->topLeft.x -= ceilThickness;
    threadData->topLeft.y += ceilThickness;

    threadData->bottomRight.x += ceilThickness;
    threadData->bottomRight.y -= ceilThickness;

    drawLineFloat( threadData->scratch, x0, y0, x1, y1, imageData->width, imageData->height, 
                    __max(thickness / 10.0f, 0.01f), (void*)brushData, writeSingleFloatBrush );

    freeBrushData(brushData);
}

void blurLineSegment(LineData* lineData, ImageData* imageData, ThreadData* threadData) {
    float blur = lineData->blur;

    if(blur == 0.0) {
        return;
    }

    int ceilBlur = ceil(blur);

    int width = imageData->width;
    int height = imageData->height;

    float* scratch = threadData->scratch;

    threadData->topLeft.x -= ceilBlur;
    threadData->topLeft.y += ceilBlur;

    threadData->bottomRight.x += ceilBlur;
    threadData->bottomRight.y -= ceilBlur;

    constrainArea(imageData, threadData);

    int baseX = threadData->topLeft.x;
    int baseY = threadData->bottomRight.y;

    int areaWidth = threadData->bottomRight.x - threadData->topLeft.x;
    int areaHeight = threadData->topLeft.y - threadData->bottomRight.y;

    int kw = (int)(blur + 2) * 2 + 1;
    int kc = kw / 2; // center of the kernel
    float* kernel = buildKernel(kw, blur);

    float* temp = (float*) malloc(areaWidth * areaHeight * sizeof(float));

    // y direction (write to temp)
    for(int y = 0; y<areaHeight; y++) {
        for(int x = 0; x<areaWidth; x++) {
            float sum = 0;
            int yReal = y + baseY;
            int xReal = x + baseX;
            for(int i = -kc;i <= kc; i++ ) {
                int y1 = reflect(height, yReal + i);
                sum += kernel[i+kc] * scratch[IMAGE_INDEX(xReal,y1,width)];
            }
            temp[IMAGE_INDEX(x,y,areaWidth)] = sum;
        }
    }

    // x direction (write to scratch)
    for(int y = 0; y<areaHeight; y++) {
        for(int x = 0; x<areaWidth; x++) {
            float sum = 0;
            int yReal = y + baseY;
            int xReal = x + baseX;
            for(int i = -kc;i<=kc;i++) {
                int x1 = reflect(areaWidth, x + i);
                if(OUTSIDE_IMAGE(x1,y,areaWidth,areaHeight)) {
                    continue;
                }
                sum += kernel[i+kc] * temp[IMAGE_INDEX(x1,y,areaWidth)];
            }
            scratch[IMAGE_INDEX(xReal, yReal, width)] = sum;
        }
    }
    
    free(temp);
    free(kernel);
}

void drawLineSegment(BitmaskData* bitmaskData, unsigned long long maskIdx, LineData* lineData, ImageData* imageData, ThreadData* threadData) {

    // preliminary pass to get the edges that the line would miss
    drawLineSegmentEdgeAware(bitmaskData->bitmask, maskIdx, lineData, imageData, threadData);

    drawLineSegmentThickness(lineData, imageData, threadData);

    blurLineSegment(lineData, imageData, threadData);

}

void drawLineSegments(float* dst, BitmaskData* bitmaskData, IslandLines* lines, ImageData* imageData, ThreadData* threadData, float multiplier) {
    int iters = lines->numLines;
    unsigned long long islandIdx = 1ULL<<(lines->islandIdx);
    for(int i = 0;i<iters;i++) {
        LineData* line = lines->lineData + i;
        drawLineSegment(bitmaskData, islandIdx, line, imageData, threadData);
        copyAndClearThreadScratch(bitmaskData, islandIdx, threadData, imageData, multiplier);
        clearThreadData(threadData);
    }
}

void copyTempToDst(ImageData* imageData, float* dst) {
    int width = imageData->width;
    int height = imageData->height;
    int numElements = width * height * 4;
    float* scratch = imageData->scratch;
    for(int i = 0;i<numElements;i+=4) {
        int sIdx = i / 4;

        // hard coded white to save memory.
        dst[i + 0] = 1.0f;
        dst[i + 1] = 1.0f;
        dst[i + 2] = 1.0f;
        dst[i + 3] = scratch[sIdx];
    }
}


void generateBitmaskTest(float* dst, ImageData* data, Island* islands, int startIdx, int endIdx) {

    float fwidth = (float)data->width;
    float fheight = (float)data->height;

    //#pragma omp parallel for
    for( int i=startIdx; i<endIdx; i++ ) {
        Island island = islands[i];
        int num = island.numTriangles * 6;
        float vals[4] = {1,1,1,1};
        for(int k = 0;k<num;k+=6) {
            int x0 = abs((int)round(island.triangles[k] * fwidth));
            int y0 = abs((int)round(island.triangles[k + 1] * fheight));
            int x1 = abs((int)round(island.triangles[k + 2] * fwidth));
            int y1 = abs((int)round(island.triangles[k + 3] * fheight));
            int x2 = abs((int)round(island.triangles[k + 4] * fwidth));
            int y2 = abs((int)round(island.triangles[k + 5] * fheight));
            drawTriangle( (void*)dst, x0, y0, x1, y1, x2, y2, data->width, data->height, vals, &writeFourFloat );
        }
    }
}

void generateEdgeHighlights( float** lineData, float* tuvData, float* multipliers, int numEntries, int width, int height, float* dst ) {

    int threads = omp_get_max_threads();

    IslandLines* lines1 = convertLineData(lineData[0], numEntries);
    IslandLines* lines2 = convertLineData(lineData[1], numEntries);
    IslandLines* lines3 = convertLineData(lineData[2], numEntries);
    Island* islands = convertIslandData(tuvData, numEntries);
    ImageData* imageData = createImageData(width, height);
    ThreadData* threadData = createThreadData(threads, imageData);
    BitmaskData* bitmaskData = createBitmaskData(width, height);


    for(int i =0;i<numEntries;i+=64) {
        int i2 = __min(i + 64, numEntries);
        generateBitmask(bitmaskData, imageData, islands, i, i2);

        #pragma omp parallel for
        for( int k = i;k < i2;k++ ) {
            ThreadData* d = threadData + omp_get_thread_num();
            drawLineSegments(dst, bitmaskData, lines1 + k, imageData, d, multipliers[0]);
            drawLineSegments(dst, bitmaskData, lines2 + k, imageData, d, multipliers[1]);
            drawLineSegments(dst, bitmaskData, lines3 + k, imageData, d, multipliers[2]);
        }

    }

    copyTempToDst(imageData, dst);
    freeStructData(bitmaskData, lines1, lines2, islands, threadData, threads, imageData);
}

// tuv data is triangulated UVs which act as a mask to determine which pixels can be written to
// uvData is the lines that represent all lines to draw distance field from
void generateDistanceField( float* uvData, int uvLen, float* tuvData, int tuvLen, int width, int height, int target, float* dst, float* retVal ) {

    if(uvLen == 0 || tuvLen == 0 || width == 0 || height == 0) {
        return;
    }

    // first, draw a mask for what pixels may be written to
    float fwidth =  (float) width;
    float fheight = (float) height;

    const float subtract = 0.0f;
    char one[1] = {1};
    char* mask = calloc(width * height, sizeof(char));
    char* tempBuffer = calloc(width * height, sizeof(char));

    EmbeddedWriteData writeData;
    writeData.writeFunc = writeSingleChar;
    writeData.argData = one;

    #pragma omp parallel for
    for( int i=0; i<tuvLen; i+=6 ) {
        int x0 = abs((int)round(tuvData[i] * fwidth - subtract));
        int y0 = abs((int)round(tuvData[i + 1] * fheight - subtract));
        int x1 = abs((int)round(tuvData[i + 2] * fwidth - subtract));
        int y1 = abs((int)round(tuvData[i + 3] * fheight - subtract));
        int x2 = abs((int)round(tuvData[i + 4] * fwidth - subtract));
        int y2 = abs((int)round(tuvData[i + 5] * fheight - subtract));
        
        drawTriangle( (void*)mask, x0, y0, x1, y1, x2, y2, width, height, one, writeSingleChar );
        drawLine( (void*)mask, x0, y0, x1, y1, width, height, &writeData, write3x3Plus );
        drawLine( (void*)mask, x1, y1, x2, y2, width, height, &writeData, write3x3Plus );
        drawLine( (void*)mask, x2, y2, x0, y0, width, height, &writeData, write3x3Plus );
    }


    // next, draw the UV lines to the image
    int distSum = 0;
    int distPixels = 0;
    char* seenPixels = (char*)calloc(width * height, sizeof(char));
    short* mapping =  (short*)calloc(width * height, sizeof(short));

    // allocate enough space for each buffer to hold the entire image
    // each list holds several x,y pairs that represent pixels to be checked next
    short* openList =   (short*)malloc(width * height * 2 * sizeof(short));
    short* swapList =   (short*)malloc(width * height * 2 * sizeof(short));
    int openLen, swapLen;

    // draw all UV lines
    #pragma omp parallel for
    for( int i=0; i<uvLen; i+=4 ) {
        const float subtract = 0.5;
        int x0 = abs((int)round(uvData[i] * fwidth - subtract));
        int y0 = abs((int)round(uvData[i + 1] * fheight - subtract));
        int x1 = abs((int)round(uvData[i + 2] * fwidth - subtract));
        int y1 = abs((int)round(uvData[i + 3] * fheight - subtract));
        drawLine( tempBuffer, x0, y0, x1, y1, width, height, one, writeSingleChar );
    }

    // fill our openList
    openLen = 0;
    for ( int x=0;x<width;x++) {
        for ( int y=0;y<height;y++) {
            int idx = IMAGE_INDEX(x,y,width);
            if(tempBuffer[idx]) {
                // mark pixels as seen
                seenPixels[idx] = 1;

                // write to openList
                openList[openLen] = x;
                openList[openLen + 1] = y;
                openLen += 2;
            }
        }
    }

    int currentValue = 0;
    int seenAny = 1;
    while(openLen != 0) {
        swapLen = 0;
        if(seenAny) {
            currentValue++;
            seenAny = 0;
        }

        // multiplied by 2 but doesn't matter
        distSum += currentValue * openLen;
        distPixels += openLen;

        for( int k=0; k<openLen; k+=2 ) {
            short xx = openList[k];
            short yy = openList[k + 1];
            for(int j=0;j<9;j++) {
                int ox = xx+j % 3 - 1;
                int oy = yy+j / 3 - 1;

                if(pixelSetMaskBoundary( seenPixels, ox, oy, width, height )) { // already processed or queued for processing
                    continue;
                }

                int idx = IMAGE_INDEX(ox, oy, width);
                char maskVal = mask[idx];
                
                seenAny |= maskVal;
                mapping[idx] = currentValue;
                seenPixels[idx] = 1;

                swapList[swapLen] = ox;
                swapList[swapLen + 1] = oy;
                swapLen += 2;
            }
        }
        // swap our lists
        short* temp = openList;
        openList = swapList;
        swapList = temp;
        openLen = swapLen;
    }

    float pixelDiff = (float)(255 - target) / 255.0 / (float) currentValue;
    // map each pixel to it's corresponding value
    #pragma omp parallel for collapse(2)
    for(int y=0; y<height; y++) {
        for(int x=0; x<width; x++) {
            float val = 1.0 - pixelDiff * (float)mapping[y * width + x];
            setPixel( dst, x, y, width, val, val, val, 1.0);
        }
    }

    free(openList);
    free(swapList);
    free(seenPixels);
    free(mapping);
    free(tempBuffer);
    free(mask);

    *retVal = (float) distSum / (float) distPixels * 4;
}

inline float toLinearRGB(float f) {
    if (f <= 0.04045) {
        return f / 12.92f;
    }
    return powf(((f + 0.055) / 1.055), 2.4f);
}

inline float tosRGB(float f) {
    if(f <= 0.0031308) {
        return f * 12.92f;
    }
    return 1.055f * powf(f, 1.0f / 2.4f) - 0.055f;
}

void compositeFinal(float* diffuse, float* ao, float* edgeHighlight, float* distanceField, float* out, int width, int height, int multiplyCount) {
    
    int loops = width * height * 4;
    #pragma omp parallel for
    for(int idx = 0;idx < loops; idx+=4) {
        float temp[4];
        float temp2[3];
        temp[0] = diffuse[idx + 0]; 
        temp[1] = diffuse[idx + 1]; 
        temp[2] = diffuse[idx + 2]; 

        temp[3] = toLinearRGB(distanceField[idx]); // sample red, they're all the same

        // perform soft light
        float er = edgeHighlight[idx + 0];
        float eg = edgeHighlight[idx + 1];
        float eb = edgeHighlight[idx + 2];
        float ea = edgeHighlight[idx + 3];

        temp2[0] = (1 - 2 * er) * powf(temp[0], 2.0f) + 2 * er * temp[0];
        temp2[1] = (1 - 2 * eg) * powf(temp[1], 2.0f) + 2 * eg * temp[1];
        temp2[2] = (1 - 2 * eb) * powf(temp[2], 2.0f) + 2 * eb * temp[2];

        temp[0] = temp2[0] * ea + temp[0] * (1 - ea);
        temp[1] = temp2[1] * ea + temp[1] * (1 - ea);
        temp[2] = temp2[2] * ea + temp[2] * (1 - ea);

        // perform multiply
        float ar = ao[idx + 0];
        float ag = ao[idx + 1];
        float ab = ao[idx + 2];

        temp[0] = temp[0] * powf(ar,multiplyCount);
        temp[1] = temp[1] * powf(ag, multiplyCount);
        temp[2] = temp[2] * powf(ab, multiplyCount);

        // write back

        out[idx + 0] = temp[0];
        out[idx + 1] = temp[1];
        out[idx + 2] = temp[2];
        out[idx + 3] = temp[3];
    }
}