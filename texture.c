#include<stdlib.h>
#include<math.h>
#include<string.h>

void setPixel(float* dst, int x, int y, int w, float r, float g, float b, float a) {
    int index = (y * w + x) << 2;
    dst[index] = r;
    dst[index + 1] = g;
    dst[index + 2] = b;
    dst[index + 3] = a;
}

int pixelSet(float* dst, int x, int y, int w, int h) {
    if(x < 0 || x >= w || y< 0 || y >=h)
        return 0;
    return dst[(y * w + x) << 2] != 0;
}

int pixelSetMask(char* buf, int x, int y, int w, int h) {
    if(x < 0 || x >= w || y< 0 || y >=h)
        return 0;
    return buf[y * w + x] != 0;
}

int pixelSetMaskBoundary(char* buf, int x, int y, int w, int h) {
    if(x < 0 || x >= w || y< 0 || y >=h)
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

void drawLine(float* dst, int x0, int y0, int x1, int y1 , int imgWidth, float r, float g, float b, float a) {
    // https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm
    int dx = abs(x1-x0);
    int sx = x0<x1 ? 1 : -1;
    int dy = -abs(y1-y0);
    int sy = y0<y1 ? 1 : -1;
    int err = dx + dy;
    int e2;
    while(1) {
        setPixel(dst,x0,y0,imgWidth,r,g,b,a);
        if(x0 == x1 && y0 == y1) {
            break;
        }
        e2 = 2 * err;
        if(e2 >=dy) {
            err+=dy;
            x0+=sx;
        }
        if(e2 <=dx) {
            err+=dx;
            y0+=sy;
        }
    }
}

void fillBottomFlatTriangle(float* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, float val) {
    float invSlope1 = (float)(x1 - x0) / (float)(y1 - y0);
    float invSlope2 = (float)(x2 - x0) / (float)(y2 - y0);

    float cx1 = x0;
    float cx2 = x0;

    for (int y=y0; y<=y2; y++) {
        drawLine( dst, cx1, y, cx2,y, imgWidth, val, val, val, val );
        cx1+=invSlope1;
        cx2+=invSlope2;
    }
}

void fillTopFlatTriangle(float* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, float val) {
    float invSlope1 = (float)(x2 - x0) / (float)(y2 - y0);
    float invSlope2 = (float)(x2 - x1) / (float)(y2 - y1);

    float cx1 = x2;
    float cx2 = x2;

    for (int y=y2; y>y0; y--) {
        drawLine( dst, cx1,y,cx2,y, imgWidth, val, val, val, val );
        cx1-=invSlope1;
        cx2-=invSlope2;
    }
}

void drawTriangle(float* dst, int x0, int y0, int x1, int y1, int x2, int y2, int imgWidth, float val) {
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
        fillBottomFlatTriangle(dst,x[0],y[0],x[1],y[1],x[2],y[2],imgWidth,val);
    } else if(y[0] == y[1]) {
        fillTopFlatTriangle(dst,x[0],y[0],x[1],y[1],x[2],y[2],imgWidth,val);
    } else {
        int x3 = (int)(x[0] + ((float)(y[1] - y[0]) / (float)(y[2] - y[0])) * (x[2] - x[0]));
        int y3 = y[1];
        fillBottomFlatTriangle(dst,x[0],y[0],x[1],y[1],x3,y3,imgWidth,val);
        fillTopFlatTriangle(dst,x[1],y[1],x3,y3,x[2],y[2],imgWidth,val);
    }
}

void generateEdgeHighlights( float* uvData, int uvLen, float* tuvData, int tuvLen, int width, int height, int thickness, float blur, float* dst ) {

    float fwidth =  (float) width;
    float fheight = (float) height;

    char* areaMask;

    // generate a mask of the inside of the UVs
    if(thickness <= 1) {
        const float subtract = 0.5; 
        #pragma omp parallel for
        for( int i=0; i<tuvLen; i+=6 ) {
            int x0 = abs((int)round(tuvData[i] * fwidth - subtract));
            int y0 = abs((int)round(tuvData[i + 1] * fheight - subtract));
            int x1 = abs((int)round(tuvData[i + 2] * fwidth - subtract));
            int y1 = abs((int)round(tuvData[i + 3] * fheight - subtract));
            int x2 = abs((int)round(tuvData[i + 4] * fwidth - subtract));
            int y2 = abs((int)round(tuvData[i + 5] * fheight - subtract));
            drawTriangle( dst, x0, y0, x1, y1, x2, y2, width, 1.0f);
        }

        #pragma omp parallel for
        for( int i=0; i<uvLen; i+=4 ) {
            int x0 = abs((int)round(uvData[i] * fwidth - subtract));
            int y0 = abs((int)round(uvData[i + 1] * fheight - subtract));
            int x1 = abs((int)round(uvData[i + 2] * fwidth - subtract));
            int y1 = abs((int)round(uvData[i + 3] * fheight - subtract));
            drawLine( dst, x0, y0, x1, y1, width, 1, 1, 1, 1 );
        }

        // now copy the mask and selectively erode to fix inaccuracies
        areaMask = (char*)calloc(width*height,sizeof(char));
        #pragma omp parallel for collapse(2)
        for ( int x=0;x<width;x++) {
            for ( int y=0;y<height;y++) {
                if(pixelSet(dst,x,y,width,height)) {
                    int j;
                    const int offsetX[4] = {0,-1,1,0};
                    const int offsetY[4] = {-1,0,0,1};
                    for(j=0;j<4;j++) {
                        if(!pixelSet( dst, x+offsetX[j], y+offsetY[j], width, height )) {
                            break;
                        }
                    }
                    if( j == 4 ) {
                        areaMask[y*width+x] = 1;
                    }
                }
            }
        }

        // reset dst
        memset(dst,0,width * height * 4 * sizeof(float));
    }

    // draw the actual lines to the array
    #pragma omp parallel for
    for( int i=0; i<uvLen; i+=4 ) {
        const float subtract = 0.5; 
        int x0 = abs((int)round(uvData[i] * fwidth - subtract));
        int y0 = abs((int)round(uvData[i + 1] * fheight - subtract));
        int x1 = abs((int)round(uvData[i + 2] * fwidth - subtract));
        int y1 = abs((int)round(uvData[i + 3] * fheight - subtract));
        drawLine( dst, x0, y0, x1, y1, width, 1, 1, 1, 1 );
    }

    // basically just dilate over and over
    if(thickness > 1) {
        char* mask1 = (char*)calloc( width * height, sizeof(char) );
        #pragma omp parallel for collapse(2)
        for ( int x=0; x<width; x++) {
            for ( int y=0; y<height; y++) {
                if(pixelSet( dst, x, y, width, height )) {
                    mask1[y * width + x] = 1;
                }
            }
        }
        char* mask2 = (char*)calloc( width * height, sizeof(char) );

        for (int i = 1;i<thickness; i++) {
            #pragma omp parallel for collapse(2)
            for ( int x=0; x<width; x++) {
                for ( int y=0; y<height; y++) {
                    for(int j=0;j<9;j++) {
                        int ox = x+j % 3 - 1;
                        int oy = y+j / 3 - 1;
                        if(pixelSetMask( mask1, ox, oy, width, height )) {
                            mask2[y * width + x] = 1;
                            break;
                        }
                    }
                }
            }
            char* t = mask1;
            mask1 = mask2;
            mask2 = t;
        }

        #pragma omp parallel for collapse(2)
        for ( int x=0;x<width;x++) {
            for ( int y=0;y<height;y++) {
                if(pixelSetMask( mask1, x, y, width, height )) {
                    setPixel( dst, x, y, width, 1.0, 1.0, 1.0, 1.0 );
                }
            }
        }
        free(mask1);
        free(mask2);
    } else {
        // selectively dilate outwards to fix errors with diagonal lines
        char* tMask = (char*)calloc( width * height, sizeof(char) );

        #pragma omp parallel for collapse(2)
        for ( int x=0; x<width; x++) {
            for ( int y=0; y<height; y++) {
                if (pixelSetMask( areaMask, x, y, width, height )) {
                    continue;
                }

                for(int j=0;j<9;j++) {
                    int ox = x+j % 3 - 1;
                    int oy = y+j / 3 - 1;
                    if(pixelSet( dst, ox, oy, width, height )) {
                        tMask[y * width + x] = 1;
                        break;
                    }
                }
            }
        }

        #pragma omp parallel for collapse(2)
        for ( int x=0;x<width;x++) {
            for ( int y=0;y<height;y++) {
                if(pixelSetMask( tMask, x, y, width, height )) {
                    setPixel( dst, x, y, width, 1.0, 1.0, 1.0, 1.0 );
                }
            }
        }

        free(areaMask);
        free(tMask);
    }

    if (blur != 0.0) {
        // finally, blur the result
        int kw = (int)(blur + 2) * 2 + 1;
        int kc = kw / 2; // center of the kernel
        float* kernel = buildKernel(kw, blur);

        float* temp = (float*)malloc(width*height*sizeof(float));

        // y direction
        #pragma omp parallel for collapse(2)
        for(int y=0; y<height; y++) {
            for(int x=0; x<width ;x++) {
                float sum = 0;
                for(int i = -kc;i<=kc;i++) {
                    int y1 = reflect(height,y-i);
                    sum+=kernel[i+kc] * pixelSet(dst,x,y1,width, height);
                }
                temp[y*width+x] = sum;
            }
        }

        // x direction
        #pragma omp parallel for collapse(2)
        for(int y=0; y<height; y++) {
            for(int x=0; x<width; x++) {
                float sum = 0;
                for(int i = -kc;i<=kc;i++) {
                    int x1 = reflect(width,x-i);
                    sum+=kernel[i+kc] * temp[y*width+x1];
                }
                setPixel( dst, x, y, width, 1.0, 1.0, 1.0, sum);
            }
        }
        free(temp);
        free(kernel);
    }
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

    #pragma omp parallel for
    for( int i=0; i<tuvLen; i+=6 ) {
        const float subtract = 0.5;
        int x0 = abs((int)round(tuvData[i] * fwidth - subtract));
        int y0 = abs((int)round(tuvData[i + 1] * fheight - subtract));
        int x1 = abs((int)round(tuvData[i + 2] * fwidth - subtract));
        int y1 = abs((int)round(tuvData[i + 3] * fheight - subtract));
        int x2 = abs((int)round(tuvData[i + 4] * fwidth - subtract));
        int y2 = abs((int)round(tuvData[i + 5] * fheight - subtract));
        drawTriangle( dst, x0, y0, x1, y1, x2, y2, width, 1.0f);
    }

    // now copy the mask
    char* mask = (char*)calloc(width*height,sizeof(char));
    #pragma omp parallel for collapse(2)
    for ( int x=0;x<width;x++) {
        for ( int y=0;y<height;y++) {
            if(pixelSet(dst,x,y,width,height)) {
                mask[y*width+x] = 1;
            }
        }
    }

    char* seenPixels = (char*)calloc(width * height,sizeof(char));
    int distSum = 0;
    int distPixels = 0;
    short* mapping =  (short*)calloc(width * height, sizeof(short));
    // allocate enough space for each buffer to hold the entire image
    // each list holds several x,y pairs that represent pixels to be checked next
    short* openList =   (short*)malloc(width * height * 2 * sizeof(short));
    short* swapList =   (short*)malloc(width * height * 2 * sizeof(short));
    int openLen, swapLen;

    // reset dst -- too lazy to write a function to draw lines to a mask
    memset(dst,0,width * height * 4 * sizeof(float));

    // draw all UV lines
    #pragma omp parallel for
    for( int i=0; i<uvLen; i+=4 ) {
        const float subtract = 0.5;
        int x0 = abs((int)round(uvData[i] * fwidth - subtract));
        int y0 = abs((int)round(uvData[i + 1] * fheight - subtract));
        int x1 = abs((int)round(uvData[i + 2] * fwidth - subtract));
        int y1 = abs((int)round(uvData[i + 3] * fheight - subtract));
        drawLine( dst, x0, y0, x1, y1, width, 1, 1, 1, 1 );
    }

    // fill our openList
    openLen = 0;
    for ( int x=0;x<width;x++) {
        for ( int y=0;y<height;y++) {
            if(pixelSet(dst,x,y,width,height)) {
                // mark pixels as seen
                seenPixels[y * width + x] = 1;

                // write to openList
                openList[openLen] = x;
                openList[openLen + 1] = y;
                openLen += 2;
            }
        }
    }

    int currentValue = 0;
    while(openLen != 0) {
        swapLen = 0;
        currentValue++;

        // multiplied by 2 but doesn't matter
        distSum += currentValue * openLen;
        distPixels += openLen;

        for( int k=0; k<openLen; k+=2 ) {
            short xx = openList[k];
            short yy = openList[k + 1];
            for(int j=0;j<9;j++) {
                int ox = xx+j % 3 - 1;
                int oy = yy+j / 3 - 1;

                if(pixelSetMaskBoundary( seenPixels, ox, oy, width, height ) || !mask[oy * width + ox]) { // already processed or queued for processing
                    continue;
                }


                mapping[oy * width + ox] = currentValue;
                seenPixels[oy * width + ox] = 1;

                swapList[swapLen] = ox;
                swapList[swapLen + 1] = oy;
                swapLen += 2;
            }
        }
        // swap our lists
        short* t = openList;
        openList = swapList;
        swapList = t;
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
    free(mask);

    *retVal = (float) distSum / (float) distPixels * 4;
}